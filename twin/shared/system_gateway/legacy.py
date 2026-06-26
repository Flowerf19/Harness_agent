"""Legacy Linux-only Bash Executor adapter.

Phase B/C keeps the Docker ``bash-executor`` running as a *legacy* Linux-only
compatibility path so existing demos do not break while the native
``system-gateway`` is being rolled out. This module is the narrow adapter
that lets a ``HostGatewayClient`` fall back to the old HTTP endpoint for a
small set of read-only commands.

It is intentionally tiny:

- Only bridges ``/health`` and a single ``system.status`` structured action.
- Refuses to bridge raw shell commands. Raw shell must go through the native
  gateway so policy + audit + HMAC auth all apply.
- Logs every call so operators can see when the legacy path is exercised.

When the native gateway is fully deployed, delete this file plus
``scripts/bash_executor_*`` and ``docker/shared/docker-compose.bash-executor.yml``.
"""
from __future__ import annotations

import json as jsonlib
import logging
from dataclasses import dataclass
from typing import Any, Optional

import aiohttp

from twin.shared.system_gateway.errors import (
    HostGatewayError,
    HostGatewayUnavailableError,
)
from twin.shared.system_gateway.types import (
    GatewayActionRequest,
    GatewayActionResponse,
    GatewayCapabilities,
    GatewayHealth,
)

logger = logging.getLogger(__name__)

LEGACY_ORIGIN = "march7-bot"
LEGACY_DEFAULT_PORT = 8374
LEGACY_ALLOWED_ACTIONS = frozenset({"system.status"})


@dataclass(frozen=True)
class LegacyBridge:
    """Configuration for the legacy bash-executor bridge."""

    executor_url: str
    timeout: int = 10
    origin: str = LEGACY_ORIGIN

    def __post_init__(self) -> None:
        object.__setattr__(self, "executor_url", self.executor_url.rstrip("/"))


class LegacyBashExecutorBridge:
    """Adapter that turns legacy bash-executor responses into gateway types.

    The native ``system-gateway`` is the long-term boundary. Until it is
    deployed on every host, this adapter lets container-side callers keep
    working via the older ``Origin``-trusted bash-executor. It is read-only by
    design: only a handful of safe actions are bridged, and raw shell is
    rejected outright so callers must migrate to the native gateway for any
    mutating operation.
    """

    def __init__(
        self,
        bridge: LegacyBridge,
        *,
        session: Optional[aiohttp.ClientSession] = None,
        owns_session: bool = True,
    ) -> None:
        self.bridge = bridge
        self._session = session
        self._owns_session = owns_session and session is None

    async def close(self) -> None:
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.bridge.timeout + 5)
            )
        return self._session

    async def health(self) -> GatewayHealth:
        """Return a synthesized health snapshot from the legacy executor."""

        url = f"{self.bridge.executor_url}/health"
        try:
            data = await self._request_json("GET", url)
        except aiohttp.ClientError as exc:
            raise HostGatewayUnavailableError(
                f"Legacy bash-executor unreachable at {self.bridge.executor_url}: {exc}"
            ) from exc

        return GatewayHealth(
            status=str(data.get("status", "ok")),
            version=None,
            platform="linux-legacy",
            uptime=_optional_int(data.get("uptime")),
        )

    async def capabilities(self) -> GatewayCapabilities:
        """Return a fixed, read-only capability report."""

        logger.info("legacy bridge: reporting read-only capabilities")
        return GatewayCapabilities(
            platform="linux-legacy",
            shells=("/bin/bash",),
            features=("legacy_bash_executor", "read_only_actions"),
            structured_actions=tuple(sorted(LEGACY_ALLOWED_ACTIONS)),
            raw_shell=False,
            unsupported=("mutating_actions", "raw_shell"),
            notes=(
                "Legacy bash-executor bridge — read-only structured actions only.",
                "Migrate to native system-gateway for mutating or raw shell.",
            ),
        )

    async def run_action(self, request: GatewayActionRequest) -> GatewayActionResponse:
        """Bridge a structured action to the legacy executor.

        Only actions in ``LEGACY_ALLOWED_ACTIONS`` are allowed. Raw shell
        requests are not bridged here — they must reach the native gateway.
        """

        if request.action not in LEGACY_ALLOWED_ACTIONS:
            logger.warning(
                "legacy bridge: refusing action %s (not in allowed list)",
                request.action,
            )
            return GatewayActionResponse(
                ok=False,
                error=f"legacy_bridge_does_not_support_action:{request.action}",
            )

        if request.action == "system.status":
            return await self._bridge_system_status(request)

        # Defensive default; should be unreachable.
        return GatewayActionResponse(ok=False, error="legacy_bridge_no_handler")

    async def _bridge_system_status(
        self, request: GatewayActionRequest
    ) -> GatewayActionResponse:
        """Run a tiny read-only command through the legacy executor."""

        # The legacy executor only knows how to run shell. We pick a strictly
        # read-only command that mimics a "system.status" payload.
        command = "uname -a && uptime"
        payload = {"command": command, "timeout": min(self.bridge.timeout, 30)}
        headers = {"Origin": self.bridge.origin, "Content-Type": "application/json"}
        url = f"{self.bridge.executor_url}/execute"
        try:
            data = await self._request_json("POST", url, json=payload, headers=headers)
        except aiohttp.ClientError as exc:
            raise HostGatewayUnavailableError(
                f"Legacy bash-executor unreachable: {exc}"
            ) from exc

        ok = data.get("exit_code", 1) == 0
        output = (data.get("stdout") or "").strip()
        error = (data.get("stderr") or "").strip() or None
        logger.info(
            "legacy bridge: action=%s ok=%s exit=%s",
            request.action,
            ok,
            data.get("exit_code"),
        )
        return GatewayActionResponse(
            ok=ok,
            output=output,
            error=error,
            exit_code=_optional_int(data.get("exit_code")),
        )

    async def _request_json(
        self,
        method: str,
        url: str,
        *,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        session = await self._get_session()
        merged = {"Origin": self.bridge.origin}
        if headers:
            merged.update(headers)
        async with session.request(method, url, json=json, headers=merged) as resp:
            raw = await resp.content.read(1_000_000)
            if resp.status >= 400:
                raise HostGatewayError(
                    f"Legacy bash-executor HTTP {resp.status}: "
                    f"{raw.decode('utf-8', 'replace')[:200]}"
                )
            data = jsonlib.loads(raw.decode("utf-8"))
            if not isinstance(data, dict):
                raise HostGatewayError(
                    "Legacy bash-executor returned invalid JSON payload"
                )
            return data


def _optional_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
