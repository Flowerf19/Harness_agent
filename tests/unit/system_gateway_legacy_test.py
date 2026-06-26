"""Unit tests for the legacy bash-executor bridge."""
from __future__ import annotations

from typing import Any

import pytest

from twin.shared.system_gateway.errors import (
    HostGatewayError,
    HostGatewayUnavailableError,
)
from twin.shared.system_gateway.legacy import (
    LEGACY_ALLOWED_ACTIONS,
    LEGACY_ORIGIN,
    LegacyBashExecutorBridge,
    LegacyBridge,
)
from twin.shared.system_gateway.types import GatewayActionRequest


def _bridge():
    return LegacyBashExecutorBridge(
        LegacyBridge(executor_url="http://legacy:8374", timeout=10)
    )


def _make_ctx(body: bytes, *, status: int = 200, json_payload: dict | None = None):
    """Build an async context manager whose response exposes both json() and read()."""

    class _Resp:
        def __init__(self):
            self.status = status
            self._body = body
            self._json = json_payload

        async def json(self):
            if self._json is not None:
                return self._json
            return json.loads(self._body.decode("utf-8"))

        async def read(self, n: int = -1) -> bytes:
            return self._body

        class content:
            @staticmethod
            async def read(n: int = 0) -> bytes:
                return body

    class _Ctx:
        async def __aenter__(self):
            return _Resp()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    return _Ctx()


@pytest.mark.asyncio
async def test_legacy_health_synthesizes_platform_marker(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_request(self, method, url, **kwargs):
        captured["headers"] = dict(kwargs.get("headers") or {})
        return _make_ctx(b'{"status":"ok","uptime":120}')

    import aiohttp
    monkeypatch.setattr(aiohttp.ClientSession, "request", fake_request)

    health = await _bridge().health()

    assert health.status == "ok"
    assert health.platform == "linux-legacy"
    assert health.uptime == 120
    assert captured["headers"]["Origin"] == LEGACY_ORIGIN


@pytest.mark.asyncio
async def test_legacy_capabilities_reports_read_only_actions():
    caps = await _bridge().capabilities()

    assert caps.platform == "linux-legacy"
    assert caps.raw_shell is False
    assert set(caps.structured_actions) == set(LEGACY_ALLOWED_ACTIONS)
    assert "mutating_actions" in caps.unsupported


@pytest.mark.asyncio
async def test_legacy_run_action_rejects_unsupported_action():
    response = await _bridge().run_action(
        GatewayActionRequest(
            action="docker.restart_container",
            arguments={"name": "march7"},
            timeout=10,
            approval_id="ok",
        )
    )

    assert response.ok is False
    assert "legacy_bridge_does_not_support_action" in (response.error or "")


@pytest.mark.asyncio
async def test_legacy_system_status_sends_origin_and_command(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_request(self, method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["headers"] = dict(kwargs.get("headers") or {})
        captured["json"] = kwargs.get("json")
        return _make_ctx(b'{"exit_code":0,"stdout":"Linux"}')

    import aiohttp
    monkeypatch.setattr(aiohttp.ClientSession, "request", fake_request)

    response = await _bridge().run_action(
        GatewayActionRequest(action="system.status", timeout=10, approval_id="ok")
    )

    assert captured["method"] == "POST"
    assert captured["url"].endswith("/execute")
    assert captured["headers"]["Origin"] == LEGACY_ORIGIN
    assert "uname" in captured["json"]["command"]
    assert response.ok is True
    assert response.output == "Linux"


@pytest.mark.asyncio
async def test_legacy_run_action_returns_unavailable_on_connection_error(monkeypatch):
    import aiohttp

    def fake_request(self, method, url, **kwargs):
        raise aiohttp.ClientConnectionError("nope")

    monkeypatch.setattr(aiohttp.ClientSession, "request", fake_request)

    with pytest.raises(HostGatewayUnavailableError):
        await _bridge().run_action(
            GatewayActionRequest(action="system.status", timeout=10, approval_id="ok")
        )


@pytest.mark.asyncio
async def test_legacy_run_action_returns_error_on_http_error(monkeypatch):
    def fake_request(self, method, url, **kwargs):
        return _make_ctx(b"forbidden", status=403)

    import aiohttp
    monkeypatch.setattr(aiohttp.ClientSession, "request", fake_request)

    with pytest.raises(HostGatewayError):
        await _bridge().run_action(
            GatewayActionRequest(action="system.status", timeout=10, approval_id="ok")
        )


def test_legacy_bridge_normalizes_url():
    bridge = LegacyBridge(executor_url="http://legacy:8374/")
    assert bridge.executor_url == "http://legacy:8374"
