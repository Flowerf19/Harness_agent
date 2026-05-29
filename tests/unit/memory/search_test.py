"""Unit tests for TimelineSearch — live Redis Stack required for most cases."""
from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta

import pytest
import redis.asyncio as aioredis

from twin.shared.memory.timeline import (
    T2Memory,
    T2Topic,
    TimelineSearch,
    TimelineStore,
    format_preflight_for_prompt,
    utc_now,
)


REDIS_URL = "redis://localhost:6379"
DIM = 8


def _vec(axis: int = 0, dim: int = DIM, weight: float = 1.0) -> list[float]:
    v = [0.0] * dim
    v[axis] = weight
    return v


class FakeEmbedder:
    def __init__(self, vector: list[float] | None = None) -> None:
        self.vector = vector if vector is not None else _vec(0)
        self.calls: list[str] = []

    async def get_embedding(self, text: str) -> list[float]:
        self.calls.append(text)
        return list(self.vector)


async def _redis_alive() -> bool:
    try:
        r = aioredis.from_url(REDIS_URL, db=0, decode_responses=True)
        await r.ping()
        await r.aclose()
        return True
    except Exception:
        return False


@pytest.fixture
async def search_ctx():
    if not await _redis_alive():
        pytest.skip("redis not available")

    suffix = uuid.uuid4().hex[:8]
    topic_prefix = f"t2search_{suffix}:topic"
    mem_prefix = f"t2search_{suffix}:mem"
    topic_index = f"idx:t2search_{suffix}:topic"
    mem_index = f"idx:t2search_{suffix}:mem"

    r = aioredis.from_url(REDIS_URL, db=0, decode_responses=True)
    store = TimelineStore(
        r, vector_dim=DIM,
        topic_prefix=topic_prefix,
        mem_prefix=mem_prefix,
        topic_index=topic_index,
        mem_index=mem_index,
    )
    await store.initialize()
    search = TimelineSearch(store=store, embedder=FakeEmbedder())

    yield search, store, r

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
    await r.aclose()


# ------------------------------------------------------------------ live-redis tests


async def test_semantic_returns_knn_excluding_superseded(search_ctx):
    search, store, _r = search_ctx
    vec = _vec(0)
    old = T2Memory(user_id="u1", content="old", embedding=vec, catalogs=["interest"])
    new = T2Memory(user_id="u1", content="new", embedding=vec, catalogs=["interest"])
    await store.upsert_memory(old)
    await store.upsert_memory(new)
    await asyncio.sleep(0.05)
    await store.mark_superseded("u1", old.memory_id, new.memory_id, change_type="correction")
    await asyncio.sleep(0.05)

    hits = await search.search("u1", query="anything", mode="semantic", limit=5)
    ids = [m.memory_id for m in hits]
    assert ids == [new.memory_id]


async def test_current_state_filters_superseded(search_ctx):
    search, store, _r = search_ctx
    vec = _vec(0)
    old = T2Memory(user_id="u1", content="old", embedding=vec,
                   topic_ids=["tp-x"], catalogs=["interest"])
    new = T2Memory(user_id="u1", content="new", embedding=vec,
                   topic_ids=["tp-x"], catalogs=["interest"])
    await store.upsert_memory(old)
    await store.upsert_memory(new)
    await asyncio.sleep(0.05)
    await store.mark_superseded("u1", old.memory_id, new.memory_id)
    await asyncio.sleep(0.05)

    hits = await search.search("u1", mode="current_state", limit=10)
    ids = [m.memory_id for m in hits]
    assert ids == [new.memory_id]

    scoped = await search.search("u1", mode="current_state", topic_id="tp-x", limit=10)
    assert [m.memory_id for m in scoped] == [new.memory_id]


async def test_by_topic_returns_full_timeline_including_superseded(search_ctx):
    search, store, _r = search_ctx
    vec = _vec(0)
    tid = "tp-time"
    a = T2Memory(user_id="u1", content="A", embedding=vec, topic_ids=[tid])
    b = T2Memory(user_id="u1", content="B", embedding=vec, topic_ids=[tid])
    await store.upsert_memory(a)
    await store.upsert_memory(b)
    await asyncio.sleep(0.05)
    await store.mark_superseded("u1", a.memory_id, b.memory_id)
    await asyncio.sleep(0.05)

    hits = await search.search("u1", mode="by_topic", topic_id=tid, limit=10)
    assert {m.memory_id for m in hits} == {a.memory_id, b.memory_id}


async def test_topic_timeline_sorts_ascending(search_ctx):
    search, store, _r = search_ctx
    vec = _vec(0)
    tid = "tp-asc"
    now = utc_now()
    m_old = T2Memory(user_id="u1", content="old", embedding=vec,
                     topic_ids=[tid], created_at=now - timedelta(hours=3))
    m_mid = T2Memory(user_id="u1", content="mid", embedding=vec,
                     topic_ids=[tid], created_at=now - timedelta(hours=1))
    m_new = T2Memory(user_id="u1", content="new", embedding=vec,
                     topic_ids=[tid], created_at=now)
    for m in (m_old, m_mid, m_new):
        await store.upsert_memory(m)
    await asyncio.sleep(0.05)

    hits = await search.search("u1", mode="topic_timeline", topic_id=tid, limit=10)
    contents = [m.content for m in hits]
    assert contents == ["old", "mid", "new"]


async def test_by_catalog_excludes_superseded_by_default(search_ctx):
    search, store, _r = search_ctx
    vec = _vec(0)
    a = T2Memory(user_id="u1", content="A", embedding=vec, catalogs=["interest"])
    b = T2Memory(user_id="u1", content="B", embedding=vec, catalogs=["interest"])
    await store.upsert_memory(a)
    await store.upsert_memory(b)
    await asyncio.sleep(0.05)
    await store.mark_superseded("u1", a.memory_id, b.memory_id)
    await asyncio.sleep(0.05)

    hits = await search.search("u1", mode="by_catalog", catalog="interest", limit=10)
    assert [m.memory_id for m in hits] == [b.memory_id]


async def test_change_log_filters_change_types(search_ctx):
    search, store, _r = search_ctx
    vec = _vec(0)
    m_new = T2Memory(user_id="u1", content="new-mem", embedding=vec, change_type="new")
    m_upd = T2Memory(user_id="u1", content="upd-mem", embedding=vec, change_type="update")
    m_cor = T2Memory(user_id="u1", content="cor-mem", embedding=vec, change_type="correction")
    for m in (m_new, m_upd, m_cor):
        await store.upsert_memory(m)
    await asyncio.sleep(0.05)

    hits = await search.search("u1", mode="change_log", limit=10)
    contents = {m.content for m in hits}
    assert contents == {"upd-mem", "cor-mem"}


async def test_recent_uses_list_recent_window(search_ctx):
    search, store, _r = search_ctx
    vec = _vec(0)
    now = utc_now()
    fresh = T2Memory(user_id="u1", content="fresh", embedding=vec, created_at=now)
    stale = T2Memory(user_id="u1", content="stale", embedding=vec,
                     created_at=now - timedelta(hours=10))
    await store.upsert_memory(fresh)
    await store.upsert_memory(stale)
    await asyncio.sleep(0.05)

    hits = await search.search("u1", mode="recent", hours=1, limit=10)
    ids = [m.memory_id for m in hits]
    assert fresh.memory_id in ids and stale.memory_id not in ids


async def test_auto_mode_resolves_semantic_when_query_only(search_ctx):
    search, store, _r = search_ctx
    vec = _vec(0)
    mem = T2Memory(user_id="u1", content="hello", embedding=vec, catalogs=["interest"])
    await store.upsert_memory(mem)
    await asyncio.sleep(0.05)

    hits = await search.search("u1", query="something", mode="auto", limit=5)
    assert [m.memory_id for m in hits] == [mem.memory_id]


async def test_auto_mode_resolves_by_topic_when_topic_id_only(search_ctx):
    search, store, _r = search_ctx
    vec = _vec(0)
    tid = "tp-auto"
    mem = T2Memory(user_id="u1", content="A", embedding=vec, topic_ids=[tid])
    await store.upsert_memory(mem)
    await asyncio.sleep(0.05)

    hits = await search.search("u1", topic_id=tid, mode="auto", limit=10)
    assert [m.memory_id for m in hits] == [mem.memory_id]


async def test_on_hit_refresh_extends_ttl(search_ctx):
    search, store, r = search_ctx
    vec = _vec(0)
    tid = "tp-ttl"
    topic = T2Topic(user_id="u1", name="ttl-topic", embedding=vec, importance=3)
    topic.topic_id = tid
    await store.upsert_topic(topic)
    mem = T2Memory(user_id="u1", content="ttl-mem", embedding=vec,
                   topic_ids=[tid], catalogs=["interest"], importance=2)
    await store.upsert_memory(mem)
    await asyncio.sleep(0.05)

    mem_key = store.mem_key("u1", mem.memory_id)
    await r.persist(mem_key)
    assert await r.ttl(mem_key) == -1

    hits = await search.search("u1", query="anything", mode="semantic", limit=5)
    assert hits

    assert await r.ttl(mem_key) > 0


async def test_empty_result_does_not_raise_or_refresh(search_ctx):
    search, _store, _r = search_ctx
    hits = await search.search("nobody", query="nothing", mode="semantic", limit=5)
    assert hits == []


async def test_recent_mode_skips_topic_refresh(search_ctx):
    search, store, _r = search_ctx
    vec = _vec(0)
    tid = "tp-skip"
    mem = T2Memory(user_id="u1", content="x", embedding=vec, topic_ids=[tid])
    await store.upsert_memory(mem)
    await asyncio.sleep(0.05)

    calls: list[tuple[str, str]] = []

    async def spy_refresh(user_id, topic_id, *, bump_access=True):
        calls.append(("refresh", topic_id))

    async def spy_extend(user_id, topic_id, top=50):
        calls.append(("extend", topic_id))
        return 0

    store.refresh_topic = spy_refresh  # type: ignore[assignment]
    store.extend_topic_memory_ttls = spy_extend  # type: ignore[assignment]

    hits = await search.search("u1", mode="recent", hours=24, limit=10)
    assert hits
    assert calls == []


async def test_preflight_helper_calls_semantic(search_ctx):
    search, store, _r = search_ctx
    vec = _vec(0)
    mem = T2Memory(user_id="u1", content="pre", embedding=vec, catalogs=["interest"])
    await store.upsert_memory(mem)
    await asyncio.sleep(0.05)

    via_preflight = await search.preflight("u1", "msg")
    via_semantic = await search.search("u1", query="msg", mode="semantic", limit=5)
    assert [m.memory_id for m in via_preflight] == [m.memory_id for m in via_semantic]


# ------------------------------------------------------------------ pure unit tests


def test_unknown_mode_raises():
    search = TimelineSearch(store=None, embedder=FakeEmbedder())  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        asyncio.run(search.search("u1", mode="bogus"))


def test_by_topic_requires_topic_id():
    search = TimelineSearch(store=None, embedder=FakeEmbedder())  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        asyncio.run(search.search("u1", mode="by_topic"))


def test_format_preflight_for_prompt_renders_when_memories_present():
    long_content = "x" * 300
    mems = [
        T2Memory(user_id="u1", content="hello", embedding=_vec(0), change_type="new"),
        T2Memory(user_id="u1", content="updated fact", embedding=_vec(0),
                 change_type="update"),
        T2Memory(user_id="u1", content=long_content, embedding=_vec(0),
                 change_type="correction"),
    ]
    out = format_preflight_for_prompt(mems)
    assert out.startswith("## Ngữ cảnh nhớ liên quan")
    assert "- hello" in out
    assert "[update]" not in "- hello"
    assert "- updated fact [update]" in out
    assert "[correction]" in out
    assert "…" in out
    truncated_line = next(line for line in out.split("\n") if "…" in line)
    assert len(truncated_line) <= 240 + len("- ") + len(" [correction]") + 1


def test_format_preflight_for_prompt_empty_returns_empty_string():
    assert format_preflight_for_prompt([]) == ""
