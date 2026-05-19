import time
from unittest.mock import AsyncMock

import pytest

from twin.evernight.consolidation_runner import ConsolidationRunResult
from twin.evernight.triggers.inactivity_trigger import InactivityTrigger


class FakeRedis:
    def __init__(self, last_active: float):
        self.key = "conversation:u1:last_active"
        self.last_active = last_active
        self.deleted = []
        self.lrange = AsyncMock()

    async def keys(self, pattern):
        return [self.key]

    async def get(self, key):
        return str(self.last_active)

    async def delete(self, key):
        self.deleted.append(key)


@pytest.mark.asyncio
async def test_inactivity_trigger_calls_runner_and_deletes_marker_on_success():
    redis = FakeRedis(last_active=time.time() - 100)
    runner = AsyncMock()
    runner.run_for_user = AsyncMock(
        return_value=ConsolidationRunResult(success=True, user_id="u1", snapshot_count=2, cleared=True)
    )
    trigger = InactivityTrigger(redis, runner, inactivity_seconds=10, poll_interval=60)

    await trigger._scan_inactive_users()

    runner.run_for_user.assert_awaited_once_with("u1", reason="inactivity")
    assert redis.deleted == [redis.key]
    redis.lrange.assert_not_called()


@pytest.mark.asyncio
async def test_inactivity_trigger_keeps_marker_on_failure():
    redis = FakeRedis(last_active=time.time() - 100)
    runner = AsyncMock()
    runner.run_for_user = AsyncMock(
        return_value=ConsolidationRunResult(success=False, user_id="u1", error="failed")
    )
    trigger = InactivityTrigger(redis, runner, inactivity_seconds=10, poll_interval=60)

    await trigger._scan_inactive_users()

    runner.run_for_user.assert_awaited_once_with("u1", reason="inactivity")
    assert redis.deleted == []
