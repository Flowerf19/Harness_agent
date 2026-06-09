"""Unit tests for InactivityTrigger (new unified-flow polling)."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from twin.evernight.triggers.inactivity_trigger import InactivityTrigger


@pytest.mark.asyncio
async def test_scan_calls_evaluate_for_every_active_scope_id():
    state_repo = AsyncMock()
    state_repo.list_active = AsyncMock(
        side_effect=lambda scope: {"user": ["u1", "u2"], "channel": ["c1"]}[scope]
    )
    policy = AsyncMock()
    policy.evaluate = AsyncMock()

    trigger = InactivityTrigger(
        state_repo=state_repo,
        summary_policy=policy,
        scopes=("user", "channel"),
        poll_interval=60,
    )
    await trigger.scan()

    assert policy.evaluate.await_count == 3
    awaited = {(call.args[0], call.args[1]) for call in policy.evaluate.await_args_list}
    assert awaited == {("user", "u1"), ("user", "u2"), ("channel", "c1")}


@pytest.mark.asyncio
async def test_scan_skips_failed_scope_listing():
    state_repo = AsyncMock()

    async def _list_active(scope):
        if scope == "user":
            raise RuntimeError("redis down")
        return ["c1"]

    state_repo.list_active = AsyncMock(side_effect=_list_active)
    policy = AsyncMock()
    policy.evaluate = AsyncMock()

    trigger = InactivityTrigger(
        state_repo=state_repo,
        summary_policy=policy,
        scopes=("user", "channel"),
    )
    await trigger.scan()

    # Should still evaluate the channel scope despite user-scope failure
    policy.evaluate.assert_awaited_once_with("channel", "c1")


@pytest.mark.asyncio
async def test_scan_continues_after_individual_evaluate_failure():
    state_repo = AsyncMock()
    state_repo.list_active = AsyncMock(return_value=["u1", "u2", "u3"])
    policy = AsyncMock()
    # Second evaluate raises; the trigger should swallow and continue.
    policy.evaluate = AsyncMock(side_effect=[None, RuntimeError("boom"), None])

    trigger = InactivityTrigger(
        state_repo=state_repo,
        summary_policy=policy,
        scopes=("user",),
    )
    await trigger.scan()

    assert policy.evaluate.await_count == 3


@pytest.mark.asyncio
async def test_scan_with_empty_state_does_nothing():
    state_repo = AsyncMock()
    state_repo.list_active = AsyncMock(return_value=[])
    policy = AsyncMock()
    policy.evaluate = AsyncMock()

    trigger = InactivityTrigger(
        state_repo=state_repo,
        summary_policy=policy,
        scopes=("user", "channel"),
    )
    await trigger.scan()

    policy.evaluate.assert_not_awaited()


@pytest.mark.asyncio
async def test_scopes_filter_restricts_iteration():
    """When only ('user',) is configured, channel scope must not be listed."""
    state_repo = AsyncMock()
    state_repo.list_active = AsyncMock(return_value=["u1"])
    policy = AsyncMock()
    policy.evaluate = AsyncMock()

    trigger = InactivityTrigger(
        state_repo=state_repo,
        summary_policy=policy,
        scopes=("user",),  # channel intentionally omitted (Evernight use case)
    )
    await trigger.scan()

    # list_active called only for "user", never "channel"
    assert state_repo.list_active.await_count == 1
    state_repo.list_active.assert_awaited_with("user")
