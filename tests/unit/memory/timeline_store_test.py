"""Unit tests for T2 TimelineStore against a live Redis Stack container.

Requires the ``march7-redis`` Redis Stack container to be running. Skips
all tests if Redis is not reachable. Uses DB 0 with a unique key prefix
and index name to avoid clobbering live data — RediSearch only indexes
keys in DB 0, so we cannot isolate by DB.
"""
from __future__ import annotations

import asyncio
import math
import uuid

import pytest

import redis.asyncio as aioredis

from twin.shared.memory.timeline import (
    CATALOGS,
    T2Memory,
    T2Topic,
    TimelineStore,
)


REDIS_URL = "redis://localhost:6379"
DIM = 8  # small dim keeps tests fast; store uses whatever dim we pass


def _make_vec(axis: int, dim: int = DIM, weight: float = 1.0) -> list[float]:
    v = [0.0] * dim
    v[axis] = weight
    return v


async def _redis_alive() -> bool:
    try:
        r = aioredis.from_url(REDIS_URL, db=0, decode_responses=True)
        await r.ping()
        await r.close()
        return True
    except Exception:
        return False


@pytest.fixture
async def store():
    if not await _redis_alive():
        pytest.skip("redis not available")

    suffix = uuid.uuid4().hex[:8]
    topic_prefix = f"t2test_{suffix}:topic"
    mem_prefix = f"t2test_{suffix}:mem"
    topic_index = f"idx:t2test_{suffix}:topic"
    mem_index = f"idx:t2test_{suffix}:mem"

    r = aioredis.from_url(REDIS_URL, db=0, decode_responses=True)

    s = TimelineStore(
        r,
        vector_dim=DIM,
        topic_prefix=topic_prefix,
        mem_prefix=mem_prefix,
        topic_index=topic_index,
        mem_index=mem_index,
    )
    await s.initialize()

    yield s

    # Cleanup: drop indexes and remove any keys we created.
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


# ---------------------------------------------------------------- index


async def test_initialize_creates_indexes(store: TimelineStore):
    info_topic = await store.redis.execute_command("FT.INFO", store.TOPIC_INDEX)
    info_mem = await store.redis.execute_command("FT.INFO", store.MEM_INDEX)
    assert info_topic is not None
    assert info_mem is not None


async def test_initialize_idempotent(store: TimelineStore):
    # Calling initialize a second time must not raise.
    await store.initialize()
    await store.initialize()


# ---------------------------------------------------------------- topic CRUD


async def test_upsert_topic_roundtrip(store: TimelineStore):
    topic = T2Topic(
        user_id="u1",
        name="phim",
        aliases=["film"],
        catalogs=["interest"],
        embedding=_make_vec(0),
        importance=4,
    )
    await store.upsert_topic(topic)
    fetched = await store.get_topic("u1", topic.topic_id)
    assert fetched is not None
    assert fetched.name == "phim"
    assert "film" in fetched.aliases
    assert fetched.catalogs == ["interest"]
    assert len(fetched.embedding) == DIM


# ---------------------------------------------------------------- memory CRUD


async def test_upsert_memory_roundtrip(store: TimelineStore):
    mem = T2Memory(
        user_id="u1",
        content="thích phim tâm lý",
        embedding=_make_vec(0),
        topic_ids=["tp1"],
        catalogs=["interest"],
        importance=3,
    )
    await store.upsert_memory(mem)
    fetched = await store.get_memory("u1", mem.memory_id)
    assert fetched is not None
    assert fetched.content == "thích phim tâm lý"
    assert fetched.topic_ids == ["tp1"]
    assert fetched.catalogs == ["interest"]


async def test_upsert_memory_fits_embedding_to_index_dim(store: TimelineStore):
    mem = T2Memory(
        user_id="u1",
        content="vector too long",
        embedding=[0.1] * (DIM + 2),
        catalogs=["interest"],
    )
    await store.upsert_memory(mem)
    fetched = await store.get_memory("u1", mem.memory_id)
    assert fetched is not None
    assert len(fetched.embedding) == DIM


# ---------------------------------------------------------------- alias find


async def test_find_topic_by_alias(store: TimelineStore):
    topic = T2Topic(
        user_id="u1",
        name="phim",
        aliases=["film", "phim_anh"],
        catalogs=["interest"],
        embedding=_make_vec(0),
    )
    await store.upsert_topic(topic)
    # Allow Redis to index.
    await asyncio.sleep(0.05)
    hit_name = await store.find_topic_by_name_or_alias("u1", "phim")
    hit_alias = await store.find_topic_by_name_or_alias("u1", "film")
    assert hit_name is not None and hit_name.topic_id == topic.topic_id
    assert hit_alias is not None and hit_alias.topic_id == topic.topic_id


# ---------------------------------------------------------------- recent topics


async def test_recent_topics_ordered_desc(store: TimelineStore):
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    a = T2Topic(user_id="u1", name="oldest", embedding=_make_vec(0),
                last_accessed=now - timedelta(hours=3))
    b = T2Topic(user_id="u1", name="middle", embedding=_make_vec(1),
                last_accessed=now - timedelta(hours=1))
    c = T2Topic(user_id="u1", name="newest", embedding=_make_vec(2),
                last_accessed=now)
    for t in (a, b, c):
        await store.upsert_topic(t)
    await asyncio.sleep(0.05)
    recent = await store.recent_topics("u1", k=5)
    assert len(recent) >= 3
    names = [t.name for t in recent[:3]]
    assert names == ["newest", "middle", "oldest"]


# ---------------------------------------------------------------- KNN topics


async def test_knn_topics_returns_nearest(store: TimelineStore):
    axis_a = _make_vec(0, weight=1.0)
    axis_b = _make_vec(1, weight=1.0)
    close_to_a = [0.99, 0.14] + [0.0] * (DIM - 2)

    t_a = T2Topic(user_id="u1", name="topic_a", embedding=axis_a)
    t_b = T2Topic(user_id="u1", name="topic_b", embedding=axis_b)
    t_close = T2Topic(user_id="u1", name="topic_close_a", embedding=close_to_a)
    for t in (t_a, t_b, t_close):
        await store.upsert_topic(t)
    await asyncio.sleep(0.1)

    hits = await store.knn_topics("u1", axis_a, k=3)
    assert hits, "expected KNN hits"
    names = [h[0].name for h in hits]
    # The exact axis_a should be the top hit.
    assert names[0] == "topic_a"
    # topic_close_a should beat topic_b.
    assert names.index("topic_close_a") < names.index("topic_b")
    # Top similarity is ~1.0.
    assert hits[0][1] > 0.9


# ---------------------------------------------------------------- KNN memories


async def test_knn_memories_excludes_superseded(store: TimelineStore):
    vec = _make_vec(0)
    mem_old = T2Memory(user_id="u1", content="old", embedding=vec,
                       catalogs=["interest"])
    mem_new = T2Memory(user_id="u1", content="new", embedding=vec,
                       catalogs=["interest"])
    await store.upsert_memory(mem_old)
    await store.upsert_memory(mem_new)
    await asyncio.sleep(0.05)

    await store.mark_superseded(
        "u1", mem_old.memory_id, mem_new.memory_id,
        change_type="correction", change_reason="user changed mind",
    )
    await asyncio.sleep(0.05)

    hits = await store.knn_memories("u1", vec, k=5, exclude_superseded=True)
    ids = [h[0].memory_id for h in hits]
    assert mem_new.memory_id in ids
    assert mem_old.memory_id not in ids


# ---------------------------------------------------------------- list_recent


async def test_list_recent_filters_time_window(store: TimelineStore):
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    fresh = T2Memory(user_id="u1", content="fresh",
                     embedding=_make_vec(0), created_at=now)
    stale = T2Memory(user_id="u1", content="stale",
                     embedding=_make_vec(0),
                     created_at=now - timedelta(hours=10))
    await store.upsert_memory(fresh)
    await store.upsert_memory(stale)
    await asyncio.sleep(0.05)

    recent = await store.list_recent("u1", hours=1, limit=10)
    ids = [m.memory_id for m in recent]
    assert fresh.memory_id in ids
    assert stale.memory_id not in ids


# ---------------------------------------------------------------- TTL extension


async def test_extend_topic_memory_ttls(store: TimelineStore):
    topic_id = "topic-extend"
    vec = _make_vec(0)
    mems = [
        T2Memory(user_id="u1", content=f"m{i}", embedding=vec,
                 topic_ids=[topic_id], catalogs=["interest"], importance=2)
        for i in range(3)
    ]
    for m in mems:
        await store.upsert_memory(m)
    await asyncio.sleep(0.05)

    # Drop existing EXPIRE so we can confirm refresh sets a new one.
    for m in mems:
        await store.redis.persist(store.mem_key("u1", m.memory_id))

    count = await store.extend_topic_memory_ttls("u1", topic_id, top=10)
    assert count == 3

    for m in mems:
        ttl = await store.redis.ttl(store.mem_key("u1", m.memory_id))
        assert ttl > 0, f"expected positive TTL for {m.memory_id}"


# ---------------------------------------------------------------- supersede


async def test_mark_superseded_links_both_directions(store: TimelineStore):
    vec = _make_vec(0)
    old = T2Memory(user_id="u1", content="A", embedding=vec, catalogs=["interest"])
    new = T2Memory(user_id="u1", content="B", embedding=vec, catalogs=["interest"])
    await store.upsert_memory(old)
    await store.upsert_memory(new)

    await store.mark_superseded(
        "u1", old.memory_id, new.memory_id,
        change_type="correction", change_reason="user flipped",
    )

    refreshed_old = await store.get_memory("u1", old.memory_id)
    refreshed_new = await store.get_memory("u1", new.memory_id)
    assert refreshed_old.superseded_by == new.memory_id
    assert refreshed_new.supersedes == old.memory_id
    assert refreshed_new.change_type == "correction"
    assert refreshed_new.change_reason == "user flipped"


# ---------------------------------------------------------------- validation


def test_max_2_catalogs_validation():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        T2Memory(
            user_id="u1", content="x",
            catalogs=["interest", "habit", "rules"],
            embedding=_make_vec(0),
        )


def test_invalid_catalog_rejected():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        T2Memory(
            user_id="u1", content="x",
            catalogs=["xyz"],
            embedding=_make_vec(0),
        )


def test_catalogs_enum_complete():
    # Sanity: catalog list matches the locked design (12 catalogs).
    assert len(CATALOGS) == 12
