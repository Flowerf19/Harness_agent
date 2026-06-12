"""Unit tests for T1 active memory."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from twin.shared.memory.active import ActiveEntry, ActiveMemory, FastPathDetector
from twin.shared.memory.active.store import ActiveStore


class FakeRedis:
    """In-memory stand-in for redis.asyncio supporting the subset T1 needs.

    Supports: JSON.SET / JSON.GET, ZADD / ZRANGE / ZREM, HSET / HGETALL, DELETE.
    """

    def __init__(self) -> None:
        self.docs: dict[str, str] = {}
        self.zsets: dict[str, dict[str, float]] = {}
        self.hashes: dict[str, dict[str, str]] = {}

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
    # the consolidator re-summarizes the same transcript on every poll.
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
    trigger.assert_awaited_once_with("user", "u1")


@pytest.mark.asyncio
async def test_threshold_not_fire_below():
    trigger = AsyncMock()
    mem = _make_memory(token_counter=lambda _: 1000, trigger=trigger)
    await mem.observe("user", "u1", "user", "anything")
    trigger.assert_not_awaited()


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
