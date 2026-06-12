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
    pass

class FakeLLM:
    pass


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
    resolver = TopicResolver(store)

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





# ---------------------------------------------------------------- user isolation


async def test_user_isolation(env):
    store, resolver, embedder, llm = env
    a_topic = T2Topic(
        user_id="userA", name="phim",
        catalogs=["interest"], embedding=_vec(1.0),
    )
    await store.upsert_topic(a_topic)
    await asyncio.sleep(0.1)



    got = await resolver.resolve("userB", "phim")
    assert got.user_id == "userB"
    assert got.topic_id != a_topic.topic_id


# ---------------------------------------------------------------- normalization


async def test_normalization_preserves_diacritics(env):
    store, resolver, embedder, llm = env


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



