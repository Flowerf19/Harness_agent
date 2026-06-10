"""Unit tests for T2 cleanup + scheduler."""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

import redis.asyncio as aioredis

from twin.shared.memory.timeline import (
    Cleanup,
    CleanupReport,
    CleanupScheduler,
    T2Memory,
    T2Topic,
    TimelineStore,
)


REDIS_URL = "redis://localhost:6379"
DIM = 8


def _vec(axis: int, dim: int = DIM) -> list[float]:
    v = [0.0] * dim
    v[axis] = 1.0
    return v


def _vec_mix(a: int, b: int, weight_b: float = 0.05, dim: int = DIM) -> list[float]:
    """Vector heavily aligned to axis a but slightly mixed with axis b."""
    v = [0.0] * dim
    v[a] = 1.0
    v[b] = weight_b
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


# ---------------------------------------------------------------- fakes


class _Response:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeLLM:
    """Returns a queued list of payloads or raises a queued exception."""

    def __init__(self, payloads):
        if isinstance(payloads, (str, Exception)):
            payloads = [payloads]
        self.payloads = list(payloads)
        self.calls: list[dict] = []

    async def generate_response(
        self, messages, system_prompt=None, use_native_tools=False,
    ):
        self.calls.append({
            "messages": messages,
            "system_prompt": system_prompt,
            "use_native_tools": use_native_tools,
        })
        if not self.payloads:
            return _Response("{}")
        item = self.payloads.pop(0)
        if isinstance(item, Exception):
            raise item
        return _Response(item)


class FakeEmbedder:
    async def get_embedding(self, text):
        return [0.0] * DIM


# ---------------------------------------------------------------- scheduler


async def test_scheduler_debounces_multiple_schedules():
    counter = {"n": 0}

    async def cb(user_id):
        counter["n"] += 1

    sched = CleanupScheduler(cb, debounce_seconds=0.05)
    sched.schedule("u1")
    sched.schedule("u1")
    sched.schedule("u1")
    await sched.flush("u1")
    assert counter["n"] == 1
    await sched.close()


async def test_scheduler_cancels_previous_pending():
    counter = {"n": 0}

    async def cb(user_id):
        counter["n"] += 1

    sched = CleanupScheduler(cb, debounce_seconds=0.05)
    sched.schedule("u1")
    await asyncio.sleep(0.01)
    sched.schedule("u1")
    await asyncio.sleep(0.15)
    assert counter["n"] == 1
    await sched.close()


async def test_scheduler_swallows_callable_errors():
    async def cb(user_id):
        raise RuntimeError("boom")

    sched = CleanupScheduler(cb, debounce_seconds=0.01)
    sched.schedule("u1")
    await asyncio.sleep(0.05)
    # Calling close after a failed run should not raise.
    await sched.close()


async def test_scheduler_logs_report_summary(caplog):
    """When the cleanup callable returns a non-trivial CleanupReport, the
    scheduler surfaces a one-line INFO summary (the report is otherwise discarded)."""
    async def cb(user_id):
        return CleanupReport(supersedes_applied=1)

    sched = CleanupScheduler(cb, debounce_seconds=0.01)
    with caplog.at_level("INFO", logger="twin.shared.memory.timeline.cleanup_scheduler"):
        sched.schedule("u1")
        await sched.flush("u1")
    await sched.close()
    assert any(
        rec.levelname == "INFO" and "supersedes=1" in rec.getMessage()
        for rec in caplog.records
    )


async def test_scheduler_no_summary_when_callable_returns_none(caplog):
    """Test callables returning None (the typed contract) must stay quiet — no
    summary line is emitted because there is no report."""
    async def cb(user_id):
        return None

    sched = CleanupScheduler(cb, debounce_seconds=0.01)
    with caplog.at_level("INFO", logger="twin.shared.memory.timeline.cleanup_scheduler"):
        sched.schedule("u1")
        await sched.flush("u1")
    await sched.close()
    assert not any(
        "supersedes=" in rec.getMessage() for rec in caplog.records
    )


class StubStore:
    """Minimal store surface for non-redis cleanup tests."""

    def __init__(self):
        self.recent_memories: list[T2Memory] = []
        self.recent_topics_list: list[T2Topic] = []

    async def list_recent(self, user_id, hours=24, limit=100):
        return list(self.recent_memories)

    async def recent_topics(self, user_id, k=50):
        return list(self.recent_topics_list)

    async def mark_superseded(self, *args, **kwargs):
        pass

    async def rewrite_topic_id_in_memories(self, *args, **kwargs):
        return 0

    async def delete_topic(self, *args, **kwargs):
        pass

    async def upsert_topic(self, t):
        pass


def test_cleanup_rejects_legacy_t3_rewrite_dependencies():
    with pytest.raises(TypeError):
        Cleanup(
            store=StubStore(),
            embedder=FakeEmbedder(),
            llm=FakeLLM("{}"),
            profile_reader=lambda user_id: "",
            profile_writer=lambda user_id, content: None,
        )


async def test_run_never_raises_on_supersede_llm_error():
    store = StubStore()
    store.recent_memories = [
        T2Memory(
            user_id="u1",
            content="Người dùng sống ở Hà Nội.",
            embedding=_vec_mix(0, 1, weight_b=0.02),
            topic_ids=[],
            catalogs=["identity"],
            importance=4,
        ),
        T2Memory(
            user_id="u1",
            content="Người dùng đã chuyển sang Đà Nẵng.",
            embedding=_vec_mix(0, 1, weight_b=0.04),
            topic_ids=[],
            catalogs=["identity"],
            importance=4,
        ),
    ]

    cleanup = Cleanup(
        store=store,
        embedder=FakeEmbedder(),
        llm=FakeLLM(RuntimeError("llm down")),
    )
    report = await cleanup.run("u1")
    assert isinstance(report, CleanupReport)
    assert any("supersede_llm" in e for e in report.errors)


async def test_supersede_parse_failure_logs_warning(caplog):
    """A non-JSON supersede verdict must be VISIBLE (WARNING) and non-fatal:
    run() still returns a CleanupReport and records no error for the parse-fail."""
    store = StubStore()
    store.recent_memories = [
        T2Memory(
            user_id="u1",
            content="Người dùng sống ở Hà Nội.",
            embedding=_vec_mix(0, 1, weight_b=0.02),
            topic_ids=[],
            catalogs=["identity"],
            importance=4,
        ),
        T2Memory(
            user_id="u1",
            content="Người dùng đã chuyển sang Đà Nẵng.",
            embedding=_vec_mix(0, 1, weight_b=0.04),
            topic_ids=[],
            catalogs=["identity"],
            importance=4,
        ),
    ]
    cleanup = Cleanup(
        store=store,
        embedder=FakeEmbedder(),
        llm=FakeLLM("not json at all"),
    )
    with caplog.at_level("WARNING", logger="twin.shared.memory.timeline.cleanup"):
        report = await cleanup.run("u1")
    assert isinstance(report, CleanupReport)
    assert any(
        rec.levelname == "WARNING" and "supersede JSON parse failed" in rec.getMessage()
        for rec in caplog.records
    )


# ---------------------------------------------------------------- redis fixture


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


# ---------------------------------------------------------------- redis-backed


async def test_t2_supersede_detection_marks_pair(store: TimelineStore):
    user_id = "user-supersede"
    # Two memories about the same fact, similar embeddings.
    m_old = T2Memory(
        user_id=user_id,
        content="Người dùng sống ở Hà Nội.",
        embedding=_vec_mix(0, 1, weight_b=0.02),
        topic_ids=[],
        catalogs=["identity"],
        importance=4,
    )
    m_new = T2Memory(
        user_id=user_id,
        content="Người dùng đã chuyển sang sống ở Đà Nẵng.",
        embedding=_vec_mix(0, 1, weight_b=0.04),
        topic_ids=[],
        catalogs=["identity"],
        importance=4,
    )
    await store.upsert_memory(m_old)
    await store.upsert_memory(m_new)

    payload = json.dumps({
        "supersedes": [{
            "old_id": m_old.memory_id,
            "new_id": m_new.memory_id,
            "change_type": "update",
            "change_reason": "moved cities",
        }],
    })
    cleanup = Cleanup(
        store=store,
        embedder=FakeEmbedder(),
        llm=FakeLLM(payload),
    )
    report = await cleanup.run(user_id)
    assert report.supersedes_applied == 1
    after_old = await store.get_memory(user_id, m_old.memory_id)
    after_new = await store.get_memory(user_id, m_new.memory_id)
    assert after_old is not None and after_old.superseded_by == m_new.memory_id
    assert after_new is not None and after_new.supersedes == m_old.memory_id
    assert after_new.change_type == "update"


async def test_topic_merge_repoints_and_deletes_loser(store: TimelineStore):
    user_id = "user-merge"
    keeper = T2Topic(
        user_id=user_id,
        name="phim ảnh",
        embedding=_vec_mix(2, 3, weight_b=0.02),
        memory_count=5,
        importance=3,
    )
    loser = T2Topic(
        user_id=user_id,
        name="phim",
        embedding=_vec_mix(2, 3, weight_b=0.04),
        memory_count=2,
        importance=3,
    )
    await store.upsert_topic(keeper)
    await store.upsert_topic(loser)

    mems: list[T2Memory] = []
    for i in range(3):
        m = T2Memory(
            user_id=user_id,
            content=f"Nội dung {i}",
            embedding=_vec(4),
            topic_ids=[loser.topic_id],
            catalogs=["interest"],
            importance=3,
        )
        await store.upsert_memory(m)
        mems.append(m)

    payload = json.dumps({"merge": True, "reason": "same topic"})
    cleanup = Cleanup(
        store=store,
        embedder=FakeEmbedder(),
        llm=FakeLLM([json.dumps({"supersedes": []}), payload]),
    )
    report = await cleanup.run(user_id)
    assert report.topics_merged == 1

    assert await store.get_topic(user_id, loser.topic_id) is None
    after_keeper = await store.get_topic(user_id, keeper.topic_id)
    assert after_keeper is not None
    assert any(a.lower() == loser.name.lower() for a in after_keeper.aliases)
    assert after_keeper.memory_count >= 5 + 2

    for m in mems:
        after = await store.get_memory(user_id, m.memory_id)
        assert after is not None
        assert keeper.topic_id in after.topic_ids
        assert loser.topic_id not in after.topic_ids


async def test_delete_topic_and_rewrite_topic_id_in_memories(store: TimelineStore):
    user_id = "user-rewrite"
    topic_a = T2Topic(
        user_id=user_id, name="A",
        embedding=_vec(5), memory_count=0, importance=3,
    )
    topic_b_id = uuid.uuid4().hex
    await store.upsert_topic(topic_a)

    mems: list[T2Memory] = []
    for i in range(3):
        m = T2Memory(
            user_id=user_id,
            content=f"x{i}",
            embedding=_vec(6),
            topic_ids=[topic_a.topic_id],
            catalogs=["interest"],
            importance=3,
        )
        await store.upsert_memory(m)
        mems.append(m)

    rewritten = await store.rewrite_topic_id_in_memories(
        user_id, topic_a.topic_id, topic_b_id,
    )
    assert rewritten == 3

    await store.delete_topic(user_id, topic_a.topic_id)
    assert await store.get_topic(user_id, topic_a.topic_id) is None

    for m in mems:
        after = await store.get_memory(user_id, m.memory_id)
        assert after is not None
        assert after.topic_ids == [topic_b_id]
