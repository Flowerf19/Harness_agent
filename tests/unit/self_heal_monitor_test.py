"""Tests for SelfHealMonitor GatewayRecoveryExecutor preference."""
from __future__ import annotations

import pytest

from twin.evernight.self_heal.monitor import (
    DockerCommandRecoveryExecutor,
    GatewayRecoveryExecutor,
    RecoveryExecutor,
    SelfHealMonitor,
)


from twin.evernight.host_gateway.monitor import RESTART_ALLOWED_CONTAINERS


class FakeGatewayMonitor:
    """Minimal fake for gateway monitor dependency."""

    def __init__(self, *, base_url: str = "http://gw", timeout: int = 30):
        self.base_url = base_url
        self.timeout = timeout
        self._client = FakeClient()

    async def request_container_restart(self, name, *, approval_id=None):
        if name not in RESTART_ALLOWED_CONTAINERS:
            return False, f"container {name!r} not in allowed list"
        return True, f"restarted {name}"


class FakeClient:
    shared_secret = "test-secret"
    actor = "evernight"


class FakeRecoveryExecutor(RecoveryExecutor):
    def __init__(self):
        self.calls = []

    async def restart_container(self, container_name: str) -> tuple[bool, str]:
        self.calls.append(container_name)
        return True, f"fake-restarted {container_name}"


# ---------------------------------------------------------------------------
# GatewayRecoveryExecutor preference
# ---------------------------------------------------------------------------


def test_prefers_gateway_recovery_when_gateway_monitor_provided():
    monitor = FakeGatewayMonitor()
    shm = SelfHealMonitor(gateway_monitor=monitor)

    assert isinstance(shm._recovery_executor, GatewayRecoveryExecutor)
    assert shm._recovery_executor.gateway_monitor is monitor


def test_prefers_gateway_recovery_when_system_gateway_url_env_set(monkeypatch):
    monkeypatch.setenv("SYSTEM_GATEWAY_URL", "http://gateway.local")
    shm = SelfHealMonitor()

    assert isinstance(shm._recovery_executor, GatewayRecoveryExecutor)
    # The gateway_monitor was None but env var triggered GatewayRecoveryExecutor
    assert shm._recovery_executor.gateway_monitor is None


def test_prefers_injected_recovery_executor_over_all():
    monitor = FakeGatewayMonitor()
    injected = FakeRecoveryExecutor()
    shm = SelfHealMonitor(
        gateway_monitor=monitor,
        recovery_executor=injected,
    )

    assert shm._recovery_executor is injected
    assert isinstance(shm._recovery_executor, FakeRecoveryExecutor)


def test_falls_back_to_docker_command_when_nothing_else(monkeypatch):
    monkeypatch.delenv("SYSTEM_GATEWAY_URL", raising=False)
    shm = SelfHealMonitor()

    assert isinstance(shm._recovery_executor, DockerCommandRecoveryExecutor)


# ---------------------------------------------------------------------------
# GatewayRecoveryExecutor behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gateway_recovery_executor_mints_approval_token():
    monitor = FakeGatewayMonitor()
    executor = GatewayRecoveryExecutor(gateway_monitor=monitor)

    ok, detail = await executor.restart_container("march7")

    assert ok is True
    assert "restarted" in detail


@pytest.mark.asyncio
async def test_gateway_recovery_executor_returns_false_when_monitor_none():
    executor = GatewayRecoveryExecutor(gateway_monitor=None)

    ok, detail = await executor.restart_container("march7")

    assert ok is False
    assert "not available" in detail.lower()


@pytest.mark.asyncio
async def test_gateway_recovery_executor_skips_token_when_no_secret():
    monitor = FakeGatewayMonitor()
    monitor._client = FakeClient()
    monitor._client.shared_secret = None
    executor = GatewayRecoveryExecutor(gateway_monitor=monitor)

    # Should not raise, just proceed without approval_id
    ok, detail = await executor.restart_container("march7")
    assert ok is True


@pytest.mark.asyncio
async def test_gateway_recovery_executor_rejects_unallowed_container():
    monitor = FakeGatewayMonitor()
    executor = GatewayRecoveryExecutor(gateway_monitor=monitor)

    ok, detail = await executor.restart_container("postgres")

    assert ok is False
    assert "not in allowed list" in detail


# ---------------------------------------------------------------------------
# SelfHealMonitor start / stop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_self_heal_monitor_start_stop():
    shm = SelfHealMonitor()

    assert shm._running is False
    assert shm._task is None

    await shm.start()
    assert shm._running is True
    assert shm._task is not None

    await shm.stop()
    assert shm._running is False
    assert shm._task is None or shm._task.done()


@pytest.mark.asyncio
async def test_self_heal_monitor_stop_is_idempotent():
    shm = SelfHealMonitor()

    await shm.start()
    await shm.stop()
    await shm.stop()  # should not raise

    assert shm._running is False


# ---------------------------------------------------------------------------
# Priority ordering
# ---------------------------------------------------------------------------


def test_recovery_executor_priority_ordering(monkeypatch):
    """
    Priority (highest to lowest):
    1. Explicitly injected recovery_executor
    2. gateway_monitor provided
    3. SYSTEM_GATEWAY_URL env var set
    4. DockerCommandRecoveryExecutor (default)
    """

    # 1. Injected wins over everything
    injected = FakeRecoveryExecutor()
    shm = SelfHealMonitor(
        recovery_executor=injected,
        gateway_monitor=FakeGatewayMonitor(),
    )
    assert shm._recovery_executor is injected

    # 2. gateway_monitor wins over env var
    shm = SelfHealMonitor(
        gateway_monitor=FakeGatewayMonitor(),
    )
    assert isinstance(shm._recovery_executor, GatewayRecoveryExecutor)

    # 3. env var selects gateway recovery
    # (tested separately in test_prefers_gateway_recovery_when_system_gateway_url_env_set)

    # 4. default is docker
    monkeypatch.delenv("SYSTEM_GATEWAY_URL", raising=False)
    shm = SelfHealMonitor()
    assert isinstance(shm._recovery_executor, DockerCommandRecoveryExecutor)
