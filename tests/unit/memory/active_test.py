"""Unit tests for T1 active memory."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from twin.shared.config.settings import Config
from twin.shared.memory.active import ActiveEntry, ActiveMemory, FastPathDetector
from twin.shared.memory.active.store import ActiveStore
from twin.shared.memory.vn_time import vn_day_str


class FakeRedis:
    """In-memory stand-in for redis.asyncio supporting the subset T1 needs.

    Supports: JSON.SET / JSON.GET, ZADD / ZRANGE / ZREM, HSET / HGETALL /
    HINCRBY, DELETE, RPUSH / EXPIRE (archive-on-trim).
    """

    def __init__(self) -> None:
        self.docs: dict[str, str] = {}
        self.zsets: dict[str, dict[str, float]] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.lists: dict[str, list[str]] = {}
        self.expire_calls: list[tuple[str, int]] = []

    async def execute_command(self, *args):
        cmd = args[0]
        if cmd == "JSON.SET":
            self.docs[args[1]] = args[3]
            return "OK"
        if cmd == "JSON.GET":
            return self.docs.get(args[1])
        raise RuntimeError(f"unsupported command: {cmd}")

    async def zadd(self, key: str, mapping: dict[str, float]):
        bucket = self.zsets.setdefault(key, {})
        bucket.update(mapping)
        return len(mapping)

    async def zrange(self, key: str, start: int, stop: int):
        bucket = self.zsets.get(key, {})
        ordered = sorted(bucket.items(), key=lambda kv: kv[1])
        if stop == -1:
            sliced = ordered[start:]
        else:
            sliced = ordered[start : stop + 1]
        return [k for k, _ in sliced]

    async def zrem(self, key: str, *members):
        bucket = self.zsets.get(key, {})
        removed = 0
        for m in members:
            if m in bucket:
                del bucket[m]
                removed += 1
        return removed

    async def hset(self, key: str, mapping: dict[str, str]):
        bucket = self.hashes.setdefault(key, {})
        bucket.update(mapping)
        return len(mapping)

    async def hincrby(self, key: str, field: str, amount: int = 1):
        bucket = self.hashes.setdefault(key, {})
        current = int(bucket.get(field, 0) or 0)
        new_value = current + amount
        bucket[field] = str(new_value)
        return new_value

    async def hgetall(self, key: str):
        return dict(self.hashes.get(key, {}))

    async def delete(self, *keys):
        n = 0
        for k in keys:
            if k in self.docs:
                del self.docs[k]
                n += 1
            if k in self.hashes:
                del self.hashes[k]
                n += 1
            if k in self.zsets:
                del self.zsets[k]
                n += 1
        return n

    async def rpush(self, key: str, *values):
        bucket = self.lists.setdefault(key, [])
        bucket.extend(values)
        return len(bucket)

    async def expire(self, key: str, seconds: int):
        self.expire_calls.append((key, seconds))
        return 1


def _make_memory(token_counter=None, trigger=None) -> ActiveMemory:
    store = ActiveStore(FakeRedis())
    return ActiveMemory(
        store=store,
        detector=FastPathDetector(),
        token_counter=token_counter,
        trigger_callback=trigger,
    )


# ---------------- store / service behaviour ----------------

@pytest.mark.asyncio
async def test_observe_appends_and_bumps_tokens():
    mem = _make_memory()
    await mem.observe("user", "u1", "user", "hello world")
    await mem.observe("user", "u1", "assistant", "hi back")
    state = await mem.store.get_state("user", "u1")
    assert state["unsummarized_tokens"] > 0
    entries = await mem.get_context("user", "u1")
    assert len(entries) == 2


@pytest.mark.asyncio
async def test_observe_concurrent_updates_both_counted():
    # Regression: two concurrent observes on the same scope must not lose an
    # update via a read-then-write race on unsummarized_tokens.
    mem = _make_memory(token_counter=lambda _: 10)
    await asyncio.gather(
        mem.observe("user", "u1", "user", "first"),
        mem.observe("user", "u1", "user", "second"),
    )
    state = await mem.store.get_state("user", "u1")
    assert state["unsummarized_tokens"] == 20


@pytest.mark.asyncio
async def test_get_context_returns_ascending_order():
    mem = _make_memory()
    a = await mem.observe("user", "u1", "user", "first")
    b = await mem.observe("user", "u1", "user", "second")
    c = await mem.observe("user", "u1", "user", "third")
    entries = await mem.get_context("user", "u1")
    assert [e.entry_id for e in entries] == [a.entry_id, b.entry_id, c.entry_id]


@pytest.mark.asyncio
async def test_trim_keeps_recent():
    mem = _make_memory()
    entries: list[ActiveEntry] = []
    for i in range(10):
        entries.append(await mem.observe("user", "u1", "user", f"msg-{i}"))

    summarized = [e.entry_id for e in entries[:7]]
    await mem.trim("user", "u1", summarized, keep_recent=5)

    remaining = await mem.get_context("user", "u1")
    remaining_ids = {e.entry_id for e in remaining}

    # Most recent 5 must survive even though some of them are also in
    # summarized list (entries 5,6 are both in summarized and in recent).
    last_five_ids = {e.entry_id for e in entries[-5:]}
    assert last_five_ids.issubset(remaining_ids)
    # Entries not in summarized list must also survive (entries 7,8,9 already
    # covered by the recent-five guard; entries 0-4 are summarized but only
    # 0-4 are not in recent-five, so they must be gone).
    deleted_expected = {e.entry_id for e in entries[:5]}
    assert deleted_expected.isdisjoint(remaining_ids)


@pytest.mark.asyncio
async def test_trim_clears_unsummarized_tokens_for_retained_entries():
    # Regression: retained-but-summarized entries (the keep_recent tail) must
    # NOT count toward unsummarized_tokens, or the scope stays hot forever and
    # the consolidation re-summarizes the same transcript on every poll.
    mem = _make_memory(token_counter=lambda _: 10)
    entries: list[ActiveEntry] = []
    for i in range(5):
        entries.append(await mem.observe("user", "u1", "user", f"msg-{i}"))

    # All 5 entries summarized; keep_recent=5 retains every one of them.
    summarized = [e.entry_id for e in entries]
    await mem.trim("user", "u1", summarized, keep_recent=5)

    state = await mem.store.get_state("user", "u1")
    assert state["unsummarized_tokens"] == 0


@pytest.mark.asyncio
async def test_trim_counts_entries_not_yet_summarized():
    # An entry that arrived after the consolidation snapshot (not in
    # summarized_entry_ids) and is still present MUST keep counting.
    mem = _make_memory(token_counter=lambda _: 10)
    entries: list[ActiveEntry] = []
    for i in range(4):
        entries.append(await mem.observe("user", "u1", "user", f"msg-{i}"))
    # A 5th message lands mid-consolidation, after the snapshot was taken.
    late = await mem.observe("user", "u1", "user", "late-arrival")

    summarized = [e.entry_id for e in entries]  # excludes `late`
    await mem.trim("user", "u1", summarized, keep_recent=5)

    state = await mem.store.get_state("user", "u1")
    # Only the late, un-summarized entry's tokens remain.
    assert state["unsummarized_tokens"] == late.tokens == 10


# ---------------- archive-on-trim (W3) ----------------

@pytest.mark.asyncio
async def test_trim_archives_deleted_entries(monkeypatch):
    monkeypatch.setattr(Config, "T1_ARCHIVE_ENABLED", True)
    monkeypatch.setattr(Config, "T1_ARCHIVE_TTL_DAYS", 90)
    mem = _make_memory()
    entries: list[ActiveEntry] = []
    for i in range(10):
        entries.append(await mem.observe("user", "u1", "user", f"msg-{i}"))

    summarized = [e.entry_id for e in entries[:7]]
    await mem.trim("user", "u1", summarized, keep_recent=5)

    redis: FakeRedis = mem.store.redis  # type: ignore[assignment]
    # Entries 0-4 were deleted (5,6 protected by keep_recent) → archived.
    day = vn_day_str(entries[0].created_at.timestamp())
    key = f"t1:archive:user:u1:{day}"
    assert key in redis.lists
    payloads = [json.loads(p) for p in redis.lists[key]]
    assert [p["entry_id"] for p in payloads] == [e.entry_id for e in entries[:5]]
    # Serialized entries must round-trip (verbatim transcript preserved).
    assert payloads[0]["content"] == "msg-0"
    assert payloads[0]["scope"] == "user"
    assert payloads[0]["created_at"]  # ISO datetime survived model_dump
    # TTL refreshed on the day key.
    assert (key, 90 * 86400) in redis.expire_calls
    # And the trim itself still happened.
    remaining_ids = {e.entry_id for e in await mem.get_context("user", "u1")}
    assert remaining_ids.isdisjoint({e.entry_id for e in entries[:5]})


@pytest.mark.asyncio
async def test_trim_archive_disabled_skips_archive_but_still_trims(monkeypatch):
    monkeypatch.setattr(Config, "T1_ARCHIVE_ENABLED", False)
    mem = _make_memory()
    entries: list[ActiveEntry] = []
    for i in range(10):
        entries.append(await mem.observe("user", "u1", "user", f"msg-{i}"))

    await mem.trim("user", "u1", [e.entry_id for e in entries[:7]], keep_recent=5)

    redis: FakeRedis = mem.store.redis  # type: ignore[assignment]
    assert redis.lists == {}
    remaining_ids = {e.entry_id for e in await mem.get_context("user", "u1")}
    assert remaining_ids.isdisjoint({e.entry_id for e in entries[:5]})


@pytest.mark.asyncio
async def test_trim_archive_failure_still_trims(monkeypatch, caplog):
    """Archive is best-effort: a failure must warn and NOT block the trim —
    blocking would leave the summarized transcript hot and re-consolidate it
    forever."""
    import logging

    monkeypatch.setattr(Config, "T1_ARCHIVE_ENABLED", True)
    mem = _make_memory()
    entries: list[ActiveEntry] = []
    for i in range(10):
        entries.append(await mem.observe("user", "u1", "user", f"msg-{i}"))

    async def exploding_archive(*args, **kwargs):
        raise RuntimeError("redis OOM")

    monkeypatch.setattr(mem.store, "archive_entries", exploding_archive)

    with caplog.at_level(logging.WARNING):
        await mem.trim("user", "u1", [e.entry_id for e in entries[:7]], keep_recent=5)

    assert any("archive-on-trim failed" in rec.message for rec in caplog.records)
    remaining_ids = {e.entry_id for e in await mem.get_context("user", "u1")}
    assert remaining_ids.isdisjoint({e.entry_id for e in entries[:5]})


@pytest.mark.asyncio
async def test_archive_entries_groups_by_vn_day():
    """Entries created on different VN days must land on separate day keys —
    a trim can carry messages from before midnight."""
    from datetime import datetime, timezone

    store = ActiveStore(FakeRedis())
    e1 = ActiveEntry(
        scope="user", scope_id="u1", role="user", content="tối qua",
        created_at=datetime(2026, 7, 2, 16, 0, tzinfo=timezone.utc),  # 23:00 VN 02/07
    )
    e2 = ActiveEntry(
        scope="user", scope_id="u1", role="user", content="sáng nay",
        created_at=datetime(2026, 7, 2, 18, 0, tzinfo=timezone.utc),  # 01:00 VN 03/07
    )

    await store.archive_entries("user", "u1", [e1, e2], ttl_seconds=86400)

    redis: FakeRedis = store.redis  # type: ignore[assignment]
    assert set(redis.lists) == {
        "t1:archive:user:u1:2026-07-02",
        "t1:archive:user:u1:2026-07-03",
    }
    assert ("t1:archive:user:u1:2026-07-02", 86400) in redis.expire_calls
    assert ("t1:archive:user:u1:2026-07-03", 86400) in redis.expire_calls


# ---------------- detector ----------------

def test_fast_path_detector_matches_identity():
    d = FastPathDetector()
    assert d.is_critical("tên tôi là Hoà") == "identity"


def test_fast_path_detector_matches_contact_email():
    d = FastPathDetector()
    assert d.is_critical("email tôi là a@b.com") == "contact"


def test_fast_path_detector_no_match():
    d = FastPathDetector()
    assert d.is_critical("ok") is None


# ---------------- threshold trigger ----------------

@pytest.mark.asyncio
async def test_threshold_trigger_fires():
    trigger = AsyncMock()
    mem = _make_memory(token_counter=lambda _: 2100, trigger=trigger)
    await mem.observe("user", "u1", "user", "anything")
    # Trigger now fires as a background task, not awaited inline.
    await asyncio.sleep(0)
    trigger.assert_awaited_once_with("user", "u1")


@pytest.mark.asyncio
async def test_threshold_not_fire_below():
    trigger = AsyncMock()
    mem = _make_memory(token_counter=lambda _: 1000, trigger=trigger)
    await mem.observe("user", "u1", "user", "anything")
    trigger.assert_not_awaited()


@pytest.mark.asyncio
async def test_threshold_trigger_does_not_block_observe():
    # observe() must return before the trigger callback resolves.
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_trigger(scope, scope_id):
        started.set()
        await release.wait()

    mem = _make_memory(token_counter=lambda _: 2100, trigger=slow_trigger)
    await mem.observe("user", "u1", "user", "anything")
    await asyncio.wait_for(started.wait(), timeout=1)
    assert not release.is_set()  # sanity: trigger is still in flight
    release.set()
    # Drain the background task so it doesn't leak into other tests.
    await asyncio.gather(*mem._pending_tasks)


@pytest.mark.asyncio
async def test_threshold_trigger_skips_when_already_in_progress():
    async def slow_side_effect(*_args):
        await asyncio.sleep(0.05)

    trigger = AsyncMock(side_effect=slow_side_effect)
    mem = _make_memory(token_counter=lambda _: 2100, trigger=trigger)
    await mem.observe("user", "u1", "user", "first")
    # Second observe while the first trigger is still in flight.
    await mem.observe("user", "u1", "user", "second")
    await asyncio.gather(*mem._pending_tasks)
    trigger.assert_awaited_once_with("user", "u1")


@pytest.mark.asyncio
async def test_threshold_trigger_respects_cooldown_after_completion():
    trigger = AsyncMock()
    mem = _make_memory(token_counter=lambda _: 2100, trigger=trigger)
    await mem.observe("user", "u1", "user", "first")
    await asyncio.gather(*mem._pending_tasks)
    trigger.assert_awaited_once_with("user", "u1")

    # Tokens are still >= threshold (e.g. consolidation returned skipped),
    # but we're within the cooldown window, so no re-fire.
    await mem.observe("user", "u1", "user", "second")
    await asyncio.sleep(0)
    trigger.assert_awaited_once_with("user", "u1")


# ---------------- topic shift / push_catalog ----------------

def test_is_topic_shift_true():
    assert ActiveMemory.is_topic_shift(["work", "work", "work"], "identity", 0.85)


def test_is_topic_shift_low_conf():
    assert not ActiveMemory.is_topic_shift(["work", "work", "work"], "identity", 0.5)


def test_is_topic_shift_unstable_buffer():
    assert not ActiveMemory.is_topic_shift(["work", "identity", "work"], "habit", 0.9)


@pytest.mark.asyncio
async def test_push_catalog_returns_shift():
    mem = _make_memory()
    assert (await mem.push_catalog("user", "u1", "work", 0.9)) is False
    assert (await mem.push_catalog("user", "u1", "work", 0.9)) is False
    assert (await mem.push_catalog("user", "u1", "work", 0.9)) is False
    shift = await mem.push_catalog("user", "u1", "identity", 0.9)
    assert shift is True
    # Ensure the catalog actually got persisted.
    state = await mem.store.get_state("user", "u1")
    assert state["recent_catalogs"][-1] == "identity"
    # Verify the rolling window cap behaviour as a sanity check.
    assert len(state["recent_catalogs"]) <= 5
    # Make sure JSON serialised payload is sane (catches accidental bytes).
    raw_state = await mem.store.redis.hgetall(
        ActiveStore._state_key("user", "u1")  # noqa: SLF001
    )
    assert json.loads(raw_state["recent_catalogs"])[-1] == "identity"
