"""Unit tests for the T3 ProfileCurationScheduler (per-user debounced curation)."""
from __future__ import annotations

import asyncio

from twin.shared.memory.profile.curation_scheduler import ProfileCurationScheduler


class RecordingCurator:
    """Records every user_id curated and returns an ok-status dict."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def curate(self, user_id: str) -> dict:
        self.calls.append(user_id)
        return {"status": "ok"}


async def test_schedule_then_flush_runs_once():
    curator = RecordingCurator()
    scheduler = ProfileCurationScheduler(curator.curate, debounce_seconds=60)

    scheduler.schedule("u1")
    await scheduler.flush("u1")

    assert curator.calls == ["u1"]


async def test_repeated_schedule_within_window_collapses_to_one_run():
    curator = RecordingCurator()
    # Long debounce so the in-flight tasks never fire on their own; flush runs once.
    scheduler = ProfileCurationScheduler(curator.curate, debounce_seconds=60)

    scheduler.schedule("u1")
    scheduler.schedule("u1")
    scheduler.schedule("u1")
    await scheduler.flush("u1")

    # Three rapid schedules debounced into a single curation run.
    assert curator.calls == ["u1"]


async def test_distinct_user_ids_schedule_independently():
    curator = RecordingCurator()
    scheduler = ProfileCurationScheduler(curator.curate, debounce_seconds=60)

    # Channel fan-out: two distinct speakers each get their own curation.
    scheduler.schedule("u1")
    scheduler.schedule("u2")
    await scheduler.flush("u1")
    await scheduler.flush("u2")

    assert sorted(curator.calls) == ["u1", "u2"]


async def test_callable_exception_is_swallowed():
    async def boom(user_id: str) -> dict:
        raise RuntimeError("curation blew up")

    scheduler = ProfileCurationScheduler(boom, debounce_seconds=60)

    scheduler.schedule("u1")
    # flush awaits the run; the exception must be swallowed, not propagated.
    await scheduler.flush("u1")


async def test_close_cancels_pending_without_firing():
    curator = RecordingCurator()
    scheduler = ProfileCurationScheduler(curator.curate, debounce_seconds=60)

    scheduler.schedule("u1")
    scheduler.schedule("u2")
    await scheduler.close()

    # Pending debounce tasks cancelled before the window elapsed → no curation ran.
    assert curator.calls == []
    # A closed scheduler refuses further work.
    scheduler.schedule("u3")
    assert curator.calls == []
