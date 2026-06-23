"""HTTP client for the native System Gateway service."""
from __future__ import annotations

import logging
import json as jsonlib
from typing import Any

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
    GatewayShellRequest,
)

logger = logging.getLogger(__name__)
MAX_RESPONSE_BYTES = 1_000_000


class HostGatewayClient:
    """Small HTTP client for System Gateway health, capabilities, and actions."""

    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout + 5)
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def health(self) -> GatewayHealth:
        data = await self._request_json("GET", "/health")
        return GatewayHealth.from_dict(data)

    async def capabilities(self) -> GatewayCapabilities:
        data = await self._request_json("GET", "/capabilities")
        return GatewayCapabilities.from_dict(data)

    async def run_action(self, request: GatewayActionRequest) -> GatewayActionResponse:
        data = await self._request_json("POST", "/actions/run", json=request.to_dict())
        return GatewayActionResponse.from_dict(data)

    async def run_shell(self, request: GatewayShellRequest) -> GatewayActionResponse:
        data = await self._request_json("POST", "/shell/run", json=request.to_dict())
        return GatewayActionResponse.from_dict(data)

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session = await self._get_session()
        url = f"{self.base_url}{path}"
        try:
            async with session.request(method, url, json=json) as response:
                raw = await response.content.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise HostGatewayError("System Gateway response exceeded size limit")
                data = _loads_json(raw, response.status)
                if response.status >= 400:
                    error = data.get("error") or data.get("message") or f"HTTP {response.status}"
                    raise HostGatewayError(str(error))
                return data
        except aiohttp.ClientConnectionError as exc:
            logger.warning("System Gateway unavailable at %s: %s", self.base_url, exc)
            raise HostGatewayUnavailableError(
                f"System Gateway is not reachable at {self.base_url}"
            ) from exc
        except aiohttp.ClientError as exc:
            raise HostGatewayError(f"System Gateway request failed: {exc}") from exc


def _loads_json(raw: bytes, status: int) -> dict[str, Any]:
    try:
        data = jsonlib.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise HostGatewayError(
            f"System Gateway returned non-JSON response: HTTP {status}"
        ) from exc
    if not isinstance(data, dict):
        raise HostGatewayError("System Gateway returned invalid JSON payload")
    return data
