from unittest.mock import AsyncMock

import pytest

from twin.evernight.consolidation_runner import ConsolidationRunner


class FakeMarch7Memory:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.cleared = False

    async def get_snapshot(self, user_id: str):
        return self.snapshot

    async def clear_session(self, user_id: str):
        self.cleared = True
        return True

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_runner_fetches_snapshot_consolidates_and_clears():
    agent = AsyncMock()
    agent.consolidate = AsyncMock(return_value=True)
    memory = FakeMarch7Memory(snapshot=[{"role": "user", "content": "hello"}])
    runner = ConsolidationRunner(agent, memory)

    result = await runner.run_for_user("u1", reason="test")

    assert result.success is True
    assert result.snapshot_count == 1
    assert result.cleared is True
    assert memory.cleared is True
    agent.consolidate.assert_awaited_once_with("u1", [{"role": "user", "content": "hello"}])


@pytest.mark.asyncio
async def test_runner_does_not_clear_when_consolidation_fails():
    agent = AsyncMock()
    agent.consolidate = AsyncMock(return_value=False)
    memory = FakeMarch7Memory(snapshot=[{"role": "user", "content": "hello"}])
    runner = ConsolidationRunner(agent, memory)

    result = await runner.run_for_user("u1", reason="test")

    assert result.success is False
    assert result.cleared is False
    assert memory.cleared is False


@pytest.mark.asyncio
async def test_runner_empty_snapshot_is_successful_noop():
    agent = AsyncMock()
    agent.consolidate = AsyncMock(return_value=True)
    memory = FakeMarch7Memory(snapshot=[])
    runner = ConsolidationRunner(agent, memory)

    result = await runner.run_for_user("u1", reason="test")

    assert result.success is True
    assert result.snapshot_count == 0
    assert result.cleared is False
    agent.consolidate.assert_not_awaited()
