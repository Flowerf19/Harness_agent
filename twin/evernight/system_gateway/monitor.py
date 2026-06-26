"""Evernight-side System Gateway monitor.

This module is read-only from the agent's perspective. It does not execute
host actions — the native `system-gateway` service is the single source of
truth for policy + audit + auth. The monitor only:

1. Polls `/health` and `/capabilities` to keep a snapshot of the gateway.
2. Surfaces a degraded/missing state through ``status_for_chat`` so Evernight
   can report the gateway state to the owner via Discord DM.
3. Provides a `restart_allowed_container` helper that replaces the legacy
   direct `/execute` self-heal path with a policy-gated structured action
   that requires owner approval.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Awaitable, Callable, Optional

import aiohttp

from twin.shared.system_gateway import (
    GatewayActionRequest,
    HostGatewayClient,
    HostGatewayError,
    HostGatewayUnavailableError,
)

logger = logging.getLogger(__name__)


DEFAULT_INTERVAL_SECONDS = 60
DEFAULT_TIMEOUT_SECONDS = 10
DEFAULT_FAILURE_THRESHOLD = 3
RESTART_ALLOWED_CONTAINERS = frozenset({"march7", "evernight"})


class GatewayMonitorStatus(str, Enum):
    """Lifecycle state of the native gateway as observed by Evernight."""

    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    MISSING = "missing"


@dataclass(frozen=True)
class GatewaySnapshot:
    """A point-in-time view of the gateway."""

    status: GatewayMonitorStatus
    platform: Optional[str] = None
    version: Optional[str] = None
    uptime: Optional[int] = None
    raw_shell_enabled: bool = False
    structured_actions: tuple[str, ...] = ()
    consecutive_failures: int = 0
    last_error: Optional[str] = None
    last_checked: Optional[float] = None

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "platform": self.platform,
            "version": self.version,
            "uptime": self.uptime,
            "raw_shell_enabled": self.raw_shell_enabled,
            "structured_actions": list(self.structured_actions),
            "consecutive_failures": self.consecutive_failures,
            "last_error": self.last_error,
            "last_checked": self.last_checked,
        }

    def render_for_chat(self) -> str:
        """Return a human-readable status line for Discord output."""

        if self.status is GatewayMonitorStatus.MISSING:
            return (
                "❌ **System Gateway chưa sẵn sàng.** "
                "Native service không phản hồi — xem `system-gateway doctor` trên host."
            )
        if self.status is GatewayMonitorStatus.UNKNOWN:
            return "⏳ **System Gateway**: chưa có snapshot (đang chờ poll đầu tiên)."
        if self.status is GatewayMonitorStatus.DEGRADED:
            return (
                f"⚠️ **System Gateway DEGRADED**: {self.consecutive_failures} lần fail liên tiếp"
                + (f" — {self.last_error}" if self.last_error else "")
            )

        # HEALTHY
        lines = [
            "✅ **System Gateway HEALTHY**",
            f"- Platform: {self.platform}",
            f"- Version: {self.version}",
        ]
        if self.uptime is not None:
            lines.append(f"- Uptime: {self.uptime}s")
        lines.append(
            f"- Raw shell: {'enabled' if self.raw_shell_enabled else 'disabled'}"
        )
        if self.structured_actions:
            lines.append(f"- Actions: {', '.join(self.structured_actions)}")
        return "\n".join(lines)


class GatewayMonitor:
    """Polls the native gateway and keeps a fresh ``GatewaySnapshot``."""

    def __init__(
        self,
        *,
        base_url: str,
        client: HostGatewayClient | None = None,
        interval: int = DEFAULT_INTERVAL_SECONDS,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        failure_threshold: int = DEFAULT_FAILURE_THRESHOLD,
        discord_adapter=None,
        notify_user_id: Optional[int] = None,
        shared_secret: str | None = None,
        http_session_factory: Optional[
            Callable[[], Awaitable[aiohttp.ClientSession]]
        ] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = client or HostGatewayClient(
            base_url=self.base_url,
            timeout=timeout,
            shared_secret=shared_secret,
            actor="evernight",
        )
        self.interval = interval
        self.timeout = timeout
        self.failure_threshold = failure_threshold
        self._discord_adapter = discord_adapter
        self._notify_user_id = notify_user_id
        self._failure_count = 0
        self._snapshot = GatewaySnapshot(status=GatewayMonitorStatus.UNKNOWN)
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._owns_session = client is None
        self._http_session_factory = http_session_factory

    @property
    def snapshot(self) -> GatewaySnapshot:
        return self._snapshot

    async def start(self) -> None:
        """Start the polling loop."""

        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info(
            "GatewayMonitor started, polling %s every %ds", self.base_url, self.interval
        )

    async def stop(self) -> None:
        """Stop the polling loop and release owned resources."""

        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._owns_session:
            await self._client.close()

    async def refresh_once(self) -> GatewaySnapshot:
        """Force a single poll and return the new snapshot.

        Used by status/doctor handlers and tests.
        """

        return await self._poll_once()

    def status_for_chat(self) -> str:
        """Return the latest snapshot rendered for owner-facing chat output."""

        return self._snapshot.render_for_chat()

    async def request_container_restart(
        self,
        container_name: str,
        *,
        approval_id: Optional[str] = None,
    ) -> tuple[bool, str]:
        """Ask the gateway to restart a container via a policy-gated action.

        This is the replacement for the legacy direct `/execute` path used by
        ``BashExecutorRecoveryExecutor``. The gateway itself enforces the
        approval binding; we just route the request through it.
        """

        if container_name not in RESTART_ALLOWED_CONTAINERS:
            return False, f"container {container_name!r} not in allowed list"

        request = GatewayActionRequest(
            action="container.restart",
            arguments={"name": container_name},
            timeout=self.timeout,
            approval_id=approval_id,
        )
        try:
            response = await self._client.run_action(request)
        except HostGatewayUnavailableError as exc:
            return False, f"gateway unavailable: {exc}"
        except HostGatewayError as exc:
            return False, f"gateway error: {exc}"

        if response.ok:
            return True, response.output or "ok"
        return False, response.error or "gateway denied action"

    async def _poll_loop(self) -> None:
        import time

        while self._running:
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                break
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("GatewayMonitor poll error: %s", exc)
            await asyncio.sleep(self.interval)

    async def _poll_once(self) -> GatewaySnapshot:
        import time

        try:
            health = await self._client.health()
            capabilities = await self._client.capabilities()
        except HostGatewayUnavailableError as exc:
            self._failure_count += 1
            self._snapshot = GatewaySnapshot(
                status=(
                    GatewayMonitorStatus.MISSING
                    if self._failure_count >= self.failure_threshold
                    else GatewayMonitorStatus.DEGRADED
                ),
                consecutive_failures=self._failure_count,
                last_error=str(exc),
                last_checked=time.time(),
            )
            logger.warning("gateway poll failed (%d): %s", self._failure_count, exc)
            await self._maybe_notify_degraded()
            return self._snapshot
        except HostGatewayError as exc:
            self._failure_count += 1
            self._snapshot = GatewaySnapshot(
                status=GatewayMonitorStatus.DEGRADED,
                consecutive_failures=self._failure_count,
                last_error=str(exc),
                last_checked=time.time(),
            )
            logger.warning("gateway poll error (%d): %s", self._failure_count, exc)
            await self._maybe_notify_degraded()
            return self._snapshot

        self._failure_count = 0
        self._snapshot = GatewaySnapshot(
            status=GatewayMonitorStatus.HEALTHY,
            platform=health.platform,
            version=health.version,
            uptime=health.uptime,
            raw_shell_enabled=capabilities.raw_shell,
            structured_actions=capabilities.structured_actions,
            consecutive_failures=0,
            last_checked=time.time(),
        )
        return self._snapshot

    async def _maybe_notify_degraded(self) -> None:
        """Notify the owner once when the monitor enters a degraded state."""

        if self._discord_adapter is None or self._notify_user_id is None:
            return
        if self._failure_count != self.failure_threshold:
            return
        try:
            await self._discord_adapter.send_dm(
                user_id=int(self._notify_user_id),
                content=(
                    "⚠️ **System Gateway DEGRADED**: "
                    f"đã {self._failure_count} lần poll liên tiếp thất bại."
                ),
            )
        except Exception:
            logger.exception("Failed to send degraded-state DM")
