"""Tests for the Evernight System Gateway monitor start/stop and notify."""
from __future__ import annotations

import asyncio

import pytest

from twin.evernight.system_gateway.monitor import (
    GatewayMonitor,
    GatewayMonitorStatus,
    GatewaySnapshot,
)
from twin.shared.system_gateway import (
    GatewayCapabilities,
    GatewayHealth,
    HostGatewayUnavailableError,
)


class _FakeClient:
    """Drop-in replacement for HostGatewayClient used in monitor tests."""

    def __init__(
        self,
        *,
        health: GatewayHealth | None = None,
        capabilities: GatewayCapabilities | None = None,
        health_exc: Exception | None = None,
        capabilities_exc: Exception | None = None,
    ):
        self._health = health or GatewayHealth(
            status="ok", version="0.1.0", platform="linux", uptime=10
        )
        self._capabilities = capabilities or GatewayCapabilities(
            platform="linux",
            shells=("/bin/sh",),
            features=("read_only_capability_report",),
            structured_actions=("system.status",),
            raw_shell=False,
        )
        self._health_exc = health_exc
        self._capabilities_exc = capabilities_exc
        self.closed = False

    async def health(self) -> GatewayHealth:
        if self._health_exc:
            raise self._health_exc
        return self._health

    async def capabilities(self) -> GatewayCapabilities:
        if self._capabilities_exc:
            raise self._capabilities_exc
        return self._capabilities

    async def close(self) -> None:
        self.closed = True


# ---------------------------------------------------------------------------
# GatewayMonitor start / stop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_monitor_start_creates_polling_task():
    client = _FakeClient()
    monitor = GatewayMonitor(base_url="http://gw", client=client, interval=999)

    assert monitor._running is False
    assert monitor._task is None

    await monitor.start()

    assert monitor._running is True
    assert monitor._task is not None
    assert not monitor._task.done()

    await monitor.stop()


@pytest.mark.asyncio
async def test_monitor_stop_cancels_task_and_closes_owned_client():
    client = _FakeClient()
    monitor = GatewayMonitor(base_url="http://gw", client=client, interval=999)
    monitor._owns_session = True

    await monitor.start()
    await monitor.stop()

    assert monitor._running is False
    assert client.closed is True
    assert monitor._task is None or monitor._task.done()


@pytest.mark.asyncio
async def test_monitor_stop_does_not_close_injected_client():
    client = _FakeClient()
    monitor = GatewayMonitor(base_url="http://gw", client=client, interval=999)
    monitor._owns_session = False

    await monitor.start()
    await monitor.stop()

    assert client.closed is False


@pytest.mark.asyncio
async def test_monitor_start_is_idempotent():
    client = _FakeClient()
    monitor = GatewayMonitor(base_url="http://gw", client=client, interval=999)

    await monitor.start()
    first_task = monitor._task

    await monitor.start()
    assert monitor._task is first_task

    await monitor.stop()


@pytest.mark.asyncio
async def test_monitor_stop_is_idempotent():
    client = _FakeClient()
    monitor = GatewayMonitor(base_url="http://gw", client=client, interval=999)

    await monitor.start()
    await monitor.stop()
    # second stop should not raise
    await monitor.stop()

    assert monitor._running is False


@pytest.mark.asyncio
async def test_monitor_poll_loop_updates_snapshot():
    client = _FakeClient()
    monitor = GatewayMonitor(base_url="http://gw", client=client, interval=0.01)

    assert monitor.snapshot.status is GatewayMonitorStatus.UNKNOWN

    await monitor.start()
    await asyncio.sleep(0.05)
    await monitor.stop()

    assert monitor.snapshot.status is GatewayMonitorStatus.HEALTHY
    assert monitor.snapshot.platform == "linux"


@pytest.mark.asyncio
async def test_monitor_poll_loop_survives_transient_errors():
    """The loop should keep running even when polls throw."""

    client = _FakeClient(health_exc=HostGatewayUnavailableError("down"))
    monitor = GatewayMonitor(base_url="http://gw", client=client, interval=0.01)

    await monitor.start()
    await asyncio.sleep(0.05)
    await monitor.stop()

    assert monitor.snapshot.status is GatewayMonitorStatus.MISSING
    assert monitor.snapshot.consecutive_failures > 0


# ---------------------------------------------------------------------------
# GatewayMonitor _maybe_notify_degraded
# ---------------------------------------------------------------------------


class _FakeDiscordAdapter:
    def __init__(self):
        self.dms: list[dict] = []

    async def send_dm(self, user_id: int, content: str) -> None:
        self.dms.append({"user_id": user_id, "content": content})


@pytest.mark.asyncio
async def test_notify_sent_exactly_at_failure_threshold():
    adapter = _FakeDiscordAdapter()
    client = _FakeClient(health_exc=HostGatewayUnavailableError("down"))
    monitor = GatewayMonitor(
        base_url="http://gw",
        client=client,
        interval=999,
        failure_threshold=3,
        discord_adapter=adapter,
        notify_user_id=726302130318868500,
    )

    # First failure: 1/3
    await monitor.refresh_once()
    assert len(adapter.dms) == 0

    # Second failure: 2/3
    await monitor.refresh_once()
    assert len(adapter.dms) == 0

    # Third failure: exactly at threshold -> notify
    await monitor.refresh_once()
    assert len(adapter.dms) == 1
    assert "DEGRADED" in adapter.dms[0]["content"]
    assert "3" in adapter.dms[0]["content"]
    assert adapter.dms[0]["user_id"] == 726302130318868500


@pytest.mark.asyncio
async def test_notify_not_sent_without_adapter():
    client = _FakeClient(health_exc=HostGatewayUnavailableError("down"))
    monitor = GatewayMonitor(
        base_url="http://gw",
        client=client,
        interval=999,
        failure_threshold=1,
        discord_adapter=None,
        notify_user_id=726302130318868500,
    )

    await monitor.refresh_once()
    # No exception, just silently skips notification
    assert monitor.snapshot.status is GatewayMonitorStatus.MISSING


@pytest.mark.asyncio
async def test_notify_not_sent_without_user_id():
    adapter = _FakeDiscordAdapter()
    client = _FakeClient(health_exc=HostGatewayUnavailableError("down"))
    monitor = GatewayMonitor(
        base_url="http://gw",
        client=client,
        interval=999,
        failure_threshold=1,
        discord_adapter=adapter,
        notify_user_id=None,
    )

    await monitor.refresh_once()
    assert len(adapter.dms) == 0


@pytest.mark.asyncio
async def test_notify_not_sent_on_subsequent_failures_past_threshold():
    adapter = _FakeDiscordAdapter()
    client = _FakeClient(health_exc=HostGatewayUnavailableError("down"))
    monitor = GatewayMonitor(
        base_url="http://gw",
        client=client,
        interval=999,
        failure_threshold=2,
        discord_adapter=adapter,
        notify_user_id=726302130318868500,
    )

    # First failure: 2/2 -> notify
    await monitor.refresh_once()
    await monitor.refresh_once()
    assert len(adapter.dms) == 1

    # Fourth failure: already past threshold, no additional notify
    await monitor.refresh_once()
    await monitor.refresh_once()
    assert len(adapter.dms) == 1


@pytest.mark.asyncio
async def test_notify_survives_adapter_exception():
    class BrokenAdapter:
        async def send_dm(self, user_id: int, content: str) -> None:
            raise RuntimeError("discord down")

    client = _FakeClient(health_exc=HostGatewayUnavailableError("down"))
    monitor = GatewayMonitor(
        base_url="http://gw",
        client=client,
        interval=999,
        failure_threshold=1,
        discord_adapter=BrokenAdapter(),
        notify_user_id=726302130318868500,
    )

    # Should not raise
    await monitor.refresh_once()
    assert monitor.snapshot.status is GatewayMonitorStatus.MISSING


@pytest.mark.asyncio
async def test_notify_not_sent_when_recovering():
    adapter = _FakeDiscordAdapter()
    failing = _FakeClient(health_exc=HostGatewayUnavailableError("down"))
    monitor = GatewayMonitor(
        base_url="http://gw",
        client=failing,
        interval=999,
        failure_threshold=2,
        discord_adapter=adapter,
        notify_user_id=726302130318868500,
    )

    # Fail twice to trigger notification
    await monitor.refresh_once()
    await monitor.refresh_once()
    assert len(adapter.dms) == 1

    # Switch to healthy client
    monitor._client = _FakeClient()
    snapshot = await monitor.refresh_once()
    assert snapshot.status is GatewayMonitorStatus.HEALTHY
    # No recovery notification (only degraded notification exists)
    assert len(adapter.dms) == 1
