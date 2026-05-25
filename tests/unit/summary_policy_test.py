"""Unit tests for SummaryPolicy — the unified summary trigger."""
from __future__ import annotations

from datetime import timedelta

import pytest

from twin.march7.memories.activate_memory.constants import (
    CHANNEL_SUMMARY_TOKEN_LIMIT,
    MAX_WORKING_TOKENS,
    SUMMARY_MAX_MESSAGES,
    SUMMARY_MIN_MESSAGES,
)
from twin.march7.memories.activate_memory.events.event_dispatcher import (
    ActiveMemoryEvent,
    EventDispatcher,
)
from twin.march7.memories.activate_memory.management.state_repository import (
    SummaryStateRepository,
)
from twin.march7.memories.activate_memory.management.summary_policy import (
    SummaryPolicy,
)
from twin.march7.memories.activate_memory.models import MemoryEntry, get_utc_now
from twin.march7.memories.activate_memory.storage.ram_storage import RamStorage


def _capture_events(dispatcher: EventDispatcher) -> list[tuple[ActiveMemoryEvent, str, dict]]:
    captured: list = []

    def _emit(event_type, scope_id, data=None):
        captured.append((event_type, scope_id, data))

    dispatcher.emit = _emit
    return captured


async def _seed_entries(storage: RamStorage, scope: str, scope_id: str, count: int, tokens_each: int):
    for i in range(count):
        entry = MemoryEntry(
            scope=scope,
            scope_id=scope_id,
            user_id=scope_id if scope == "user" else f"author_{i}",
            role="user",
            content=f"message-{i}",
            tokens=tokens_each,
        )
        await storage.save_entry(entry)


# ---------------------------------------------------------------------------
# token_limit trigger
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_token_limit_triggers_summary_requested():
    storage = RamStorage()
    repo = SummaryStateRepository()
    dispatcher = EventDispatcher()
    captured = _capture_events(dispatcher)
    policy = SummaryPolicy(storage, repo, dispatcher)

    await _seed_entries(storage, "user", "u1", count=2, tokens_each=MAX_WORKING_TOKENS)
    state = await repo.get("user", "u1")
    state.unsummarized_message_count = 2
    state.unsummarized_token_count = 2 * MAX_WORKING_TOKENS
    await repo.save(state)

    await policy.evaluate("user", "u1")
    assert len(captured) == 1
    event_type, scope_id, payload = captured[0]
    assert event_type == ActiveMemoryEvent.SUMMARY_REQUESTED
    assert payload["scope"] == "user"
    assert payload["scope_id"] == "u1"
    assert payload["reason"] == "token_limit"


@pytest.mark.asyncio
async def test_channel_token_limit_uses_channel_threshold():
    storage = RamStorage()
    repo = SummaryStateRepository()
    dispatcher = EventDispatcher()
    captured = _capture_events(dispatcher)
    policy = SummaryPolicy(storage, repo, dispatcher)

    await _seed_entries(storage, "channel", "c1", count=2, tokens_each=CHANNEL_SUMMARY_TOKEN_LIMIT)
    state = await repo.get("channel", "c1")
    state.unsummarized_token_count = 2 * CHANNEL_SUMMARY_TOKEN_LIMIT
    state.unsummarized_message_count = 2
    await repo.save(state)

    await policy.evaluate("channel", "c1")
    assert captured and captured[0][2]["reason"] == "token_limit"


# ---------------------------------------------------------------------------
# message_count trigger
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_message_count_triggers_summary_requested():
    storage = RamStorage()
    repo = SummaryStateRepository()
    dispatcher = EventDispatcher()
    captured = _capture_events(dispatcher)
    policy = SummaryPolicy(storage, repo, dispatcher)

    await _seed_entries(storage, "channel", "c1", count=SUMMARY_MAX_MESSAGES, tokens_each=1)
    state = await repo.get("channel", "c1")
    state.unsummarized_message_count = SUMMARY_MAX_MESSAGES
    state.unsummarized_token_count = SUMMARY_MAX_MESSAGES
    await repo.save(state)

    await policy.evaluate("channel", "c1")
    assert captured and captured[0][2]["reason"] == "message_count"


# ---------------------------------------------------------------------------
# idle trigger
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_idle_triggers_when_silent_long_enough():
    storage = RamStorage()
    repo = SummaryStateRepository()
    dispatcher = EventDispatcher()
    captured = _capture_events(dispatcher)
    policy = SummaryPolicy(storage, repo, dispatcher)

    await _seed_entries(storage, "user", "u1", count=SUMMARY_MIN_MESSAGES, tokens_each=1)
    state = await repo.get("user", "u1")
    state.unsummarized_message_count = SUMMARY_MIN_MESSAGES
    state.unsummarized_token_count = SUMMARY_MIN_MESSAGES
    state.last_activity_at = get_utc_now() - timedelta(hours=2)
    await repo.save(state)

    await policy.evaluate("user", "u1")
    assert captured and captured[0][2]["reason"] == "idle"


@pytest.mark.asyncio
async def test_idle_does_not_trigger_below_min_messages():
    storage = RamStorage()
    repo = SummaryStateRepository()
    dispatcher = EventDispatcher()
    captured = _capture_events(dispatcher)
    policy = SummaryPolicy(storage, repo, dispatcher)

    await _seed_entries(storage, "user", "u1", count=5, tokens_each=1)
    state = await repo.get("user", "u1")
    state.unsummarized_message_count = 5
    state.unsummarized_token_count = 5
    state.last_activity_at = get_utc_now() - timedelta(hours=2)
    await repo.save(state)

    await policy.evaluate("user", "u1")
    assert captured == []


# ---------------------------------------------------------------------------
# concurrency guard
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_summary_in_progress_blocks_re_trigger():
    storage = RamStorage()
    repo = SummaryStateRepository()
    dispatcher = EventDispatcher()
    captured = _capture_events(dispatcher)
    policy = SummaryPolicy(storage, repo, dispatcher)

    await _seed_entries(storage, "user", "u1", count=2, tokens_each=MAX_WORKING_TOKENS)
    state = await repo.get("user", "u1")
    state.unsummarized_message_count = 2
    state.unsummarized_token_count = 2 * MAX_WORKING_TOKENS
    state.summary_in_progress = True
    state.locked_until = get_utc_now() + timedelta(minutes=5)
    await repo.save(state)

    await policy.evaluate("user", "u1")
    assert captured == []


@pytest.mark.asyncio
async def test_locked_until_past_allows_retrigger():
    storage = RamStorage()
    repo = SummaryStateRepository()
    dispatcher = EventDispatcher()
    captured = _capture_events(dispatcher)
    policy = SummaryPolicy(storage, repo, dispatcher)

    await _seed_entries(storage, "user", "u1", count=2, tokens_each=MAX_WORKING_TOKENS)
    state = await repo.get("user", "u1")
    state.unsummarized_message_count = 2
    state.unsummarized_token_count = 2 * MAX_WORKING_TOKENS
    state.summary_in_progress = True
    state.locked_until = get_utc_now() - timedelta(minutes=5)  # expired
    await repo.save(state)

    await policy.evaluate("user", "u1")
    assert captured and captured[0][2]["reason"] == "token_limit"


# ---------------------------------------------------------------------------
# below thresholds — no trigger
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_below_all_thresholds_does_not_trigger():
    storage = RamStorage()
    repo = SummaryStateRepository()
    dispatcher = EventDispatcher()
    captured = _capture_events(dispatcher)
    policy = SummaryPolicy(storage, repo, dispatcher)

    await _seed_entries(storage, "user", "u1", count=3, tokens_each=100)
    state = await repo.get("user", "u1")
    state.unsummarized_message_count = 3
    state.unsummarized_token_count = 300
    await repo.save(state)

    await policy.evaluate("user", "u1")
    assert captured == []
