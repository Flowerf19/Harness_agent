"""Unit tests for TopicResolver against a live Redis Stack container.

Skips if Redis is unreachable. Uses DB 0 with a unique prefix per test
(RediSearch indexes only DB 0).
"""
from __future__ import annotations

import asyncio
import uuid

import pytest
import redis.asyncio as aioredis

from twin.shared.memory.timeline import T2Topic, TimelineStore, TopicResolver


REDIS_URL = "redis://localhost:6379"
DIM = 1024  # match production; needed for the dim==1024 acceptance test


def _vec(*components: float) -> list[float]:
    """Build a DIM-length vector from leading components."""
    v = list(components) + [0.0] * (DIM - len(components))
    return v[:DIM]


class FakeEmbedder:
    def __init__(self) -> None:
        self.vectors: dict[str, list[float]] = {}
        self.default = _vec(1.0)

    async def get_embedding(self, text: str) -> list[float]:
        return self.vectors.get(text, self.default)


class _LLMResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeLLM:
    def __init__(self) -> None:
        self.responses: list[str] = []
        self.calls: list[tuple] = []

    async def generate_response(
        self, messages, system_prompt=None, use_native_tools=False
    ):
        self.calls.append((messages, system_prompt))
        resp = self.responses.pop(0) if self.responses else "NO"
        return _LLMResponse(resp)


async def _redis_alive() -> bool:
    try:
        r = aioredis.from_url(REDIS_URL, db=0, decode_responses=True)
        await r.ping()
        await r.close()
        return True
    except Exception:
        return False


@pytest.fixture
async def env():
    if not await _redis_alive():
        pytest.skip("redis not available")

    suffix = uuid.uuid4().hex[:8]
    topic_prefix = f"t2rtest_{suffix}:topic"
    mem_prefix = f"t2rtest_{suffix}:mem"
    topic_index = f"idx:t2rtest_{suffix}:topic"
    mem_index = f"idx:t2rtest_{suffix}:mem"

    r = aioredis.from_url(REDIS_URL, db=0, decode_responses=True)
    store = TimelineStore(
        r,
        vector_dim=DIM,
        topic_prefix=topic_prefix,
        mem_prefix=mem_prefix,
        topic_index=topic_index,
        mem_index=mem_index,
    )
    await store.initialize()

    embedder = FakeEmbedder()
    llm = FakeLLM()
    resolver = TopicResolver(store, embedder, llm)

    yield store, resolver, embedder, llm

    for idx in (topic_index, mem_index):
        try:
            await r.execute_command("FT.DROPINDEX", idx)
        except Exception:
            pass
    for prefix in (topic_prefix, mem_prefix):
        async for key in r.scan_iter(match=f"{prefix}:*"):
            try:
                await r.delete(key)
            except Exception:
                pass
    await r.close()


# ---------------------------------------------------------------- Stage 1


async def test_stage1_exact_name_hits(env):
    store, resolver, embedder, llm = env
    existing = T2Topic(
        user_id="u1", name="phim ảnh",
        catalogs=["interest"], embedding=_vec(1.0),
    )
    await store.upsert_topic(existing)
    await asyncio.sleep(0.05)

    got = await resolver.resolve("u1", "Phim Ảnh")
    assert got.topic_id == existing.topic_id
    assert not llm.calls, "LLM must not be called on exact match"


async def test_stage1_alias_hits(env):
    store, resolver, embedder, llm = env
    existing = T2Topic(
        user_id="u1", name="phim ảnh", aliases=["film"],
        catalogs=["interest"], embedding=_vec(1.0),
    )
    await store.upsert_topic(existing)
    await asyncio.sleep(0.05)

    got = await resolver.resolve("u1", "FILM")
    assert got.topic_id == existing.topic_id
    assert not llm.calls


# ---------------------------------------------------------------- Stage 2


async def test_stage2_knn_auto_merge(env):
    store, resolver, embedder, llm = env
    # Existing topic vector close to query (cos ~0.99).
    existing = T2Topic(
        user_id="u1", name="phim",
        catalogs=["interest"], embedding=_vec(0.99, 0.14),
    )
    await store.upsert_topic(existing)
    await asyncio.sleep(0.1)

    # Query vector for "Sony phim" → [1.0, 0.0, ...] → cos with existing ~0.99.
    embedder.vectors["Sony phim"] = _vec(1.0)

    got = await resolver.resolve("u1", "Sony phim")
    assert got.topic_id == existing.topic_id
    assert not llm.calls, "LLM must not be called when auto-threshold met"
    # Alias was added.
    refreshed = await store.get_topic("u1", existing.topic_id)
    assert "Sony phim" in refreshed.aliases


# ---------------------------------------------------------------- Stage 3


async def test_stage3_llm_borderline_yes(env):
    store, resolver, embedder, llm = env
    # cos([1,0], [0.83,0.56]) ≈ 0.83 → borderline.
    existing = T2Topic(
        user_id="u1", name="phim hành động",
        catalogs=["interest"], embedding=_vec(0.83, 0.56),
    )
    await store.upsert_topic(existing)
    await asyncio.sleep(0.1)

    embedder.vectors["action movies"] = _vec(1.0)
    llm.responses = ["YES"]

    got = await resolver.resolve("u1", "action movies")
    assert got.topic_id == existing.topic_id
    assert len(llm.calls) == 1
    refreshed = await store.get_topic("u1", existing.topic_id)
    assert "action movies" in refreshed.aliases


async def test_stage3_llm_borderline_no(env):
    store, resolver, embedder, llm = env
    existing = T2Topic(
        user_id="u1", name="phim hành động",
        catalogs=["interest"], embedding=_vec(0.83, 0.56),
    )
    await store.upsert_topic(existing)
    await asyncio.sleep(0.1)

    embedder.vectors["chess"] = _vec(1.0)
    llm.responses = ["NO"]

    got = await resolver.resolve("u1", "chess")
    assert got.topic_id != existing.topic_id
    assert got.name == "chess"
    assert len(llm.calls) == 1


# ---------------------------------------------------------------- Stage 4


async def test_stage4_create_new_when_below_threshold(env):
    store, resolver, embedder, llm = env
    # cos([1,0], [0.5, 0.87]) = 0.5 → below 0.75.
    existing = T2Topic(
        user_id="u1", name="cooking",
        catalogs=["interest"], embedding=_vec(0.5, 0.87),
    )
    await store.upsert_topic(existing)
    await asyncio.sleep(0.1)

    embedder.vectors["Skydiving"] = _vec(1.0)

    got = await resolver.resolve("u1", "Skydiving")
    assert got.topic_id != existing.topic_id
    assert got.name == "skydiving"
    assert "Skydiving" in got.aliases  # original kept as alias
    assert not llm.calls, "LLM must not be invoked below llm_threshold"


# ---------------------------------------------------------------- user isolation


async def test_user_isolation(env):
    store, resolver, embedder, llm = env
    a_topic = T2Topic(
        user_id="userA", name="phim",
        catalogs=["interest"], embedding=_vec(1.0),
    )
    await store.upsert_topic(a_topic)
    await asyncio.sleep(0.1)

    embedder.vectors["phim"] = _vec(1.0)

    got = await resolver.resolve("userB", "phim")
    assert got.user_id == "userB"
    assert got.topic_id != a_topic.topic_id


# ---------------------------------------------------------------- normalization


async def test_normalization_preserves_diacritics(env):
    store, resolver, embedder, llm = env
    embedder.vectors["Phim Tâm Lý"] = _vec(1.0)

    got = await resolver.resolve("u1", "Phim Tâm Lý")
    assert got.name == "phim tâm lý"
    assert "Phim Tâm Lý" in got.aliases


# ---------------------------------------------------------------- alias dedup


async def test_alias_not_duplicated(env):
    store, resolver, embedder, llm = env
    existing = T2Topic(
        user_id="u1", name="phim ảnh",
        catalogs=["interest"], embedding=_vec(1.0),
    )
    await store.upsert_topic(existing)
    await asyncio.sleep(0.05)

    # Call twice with non-canonical casing — should not duplicate.
    await resolver.resolve("u1", "Phim Ảnh")
    await resolver.resolve("u1", "Phim Ảnh")
    await asyncio.sleep(0.05)

    refreshed = await store.get_topic("u1", existing.topic_id)
    # Either no alias added (matches name normalized) or only one.
    lowered = [a.lower() for a in refreshed.aliases]
    assert len(lowered) == len(set(lowered))


# ---------------------------------------------------------------- new topic dim


async def test_create_new_attaches_embedding_dim_1024(env):
    store, resolver, embedder, llm = env
    embedder.vectors["novel topic xyz"] = _vec(1.0)

    got = await resolver.resolve("u1", "novel topic xyz")
    assert len(got.embedding) == 1024
