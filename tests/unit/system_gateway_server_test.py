"""Integration tests for the native System Gateway aiohttp app.

These tests exercise the middleware chain directly without binding a real
socket so they run inside restrictive sandboxes. We call handlers via the
auth_middleware using aiohttp's make_mocked_request.
"""
from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path

import pytest
from aiohttp.test_utils import make_mocked_request

# Ensure the native gateway package is importable from the repo root.
SERVICES_ROOT = Path(__file__).resolve().parents[2] / "services"
if str(SERVICES_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICES_ROOT))

from twin.shared.system_gateway.auth import (
    headers_from_signed,
    mint_approval_token,
    sign_request,
)

from system_gateway.config import GatewayConfig
from system_gateway.server import (
    STATE_KEY,
    capabilities,
    create_app,
    health,
    run_action,
    run_shell,
    self_update,
    auth_middleware,
)
from system_gateway.state import SERVICE_VERSION


SECRET = "phase-b-shared-secret"


def _config(**overrides):
    kwargs = dict(raw_shell_enabled=False, shared_secret=SECRET)
    kwargs.update(overrides)
    return GatewayConfig(**kwargs)


def _signed_headers(method: str, path: str, body: bytes, *, secret: str = SECRET, actor: str = "march7"):
    signed = sign_request(
        secret=secret,
        method=method,
        path=path,
        actor=actor,
        body=body,
    )
    return headers_from_signed(signed)


def _token(action: str = "system.status", *, actor: str = "march7", secret: str = SECRET, **kwargs):
    return mint_approval_token(secret=secret, action=action, actor=actor, **kwargs)


class _AsyncBytesPayload:
    """Minimal async-readable body payload for make_mocked_request."""

    def __init__(self, data: bytes) -> None:
        self._buf = io.BytesIO(data)

    async def read(self, n: int = -1) -> bytes:
        return self._buf.read(n)

    async def readany(self) -> bytes:
        return self._buf.read()

    async def readchunk(self) -> tuple[bytes, int]:
        return self._buf.read(), self._buf.tell()


def _build_request(app, method: str, path: str, body: bytes = b"", extra_headers=None):
    """Create a mocked request bound to ``app`` and preloaded body/headers."""

    headers = dict(extra_headers or {})
    if method == "POST" and body:
        payload = _AsyncBytesPayload(body)
    else:
        payload = None
    request = make_mocked_request(method, path, headers=headers, payload=payload)
    request._app = app
    return request


async def test_health_endpoint_is_public():
    app = create_app(_config())
    request = _build_request(app, "GET", "/health")
    response = await health(request)
    assert response.status == 200
    payload = json.loads(response.text)
    assert payload["status"] == "ok"
    assert payload["service"] == "system_gateway"
    assert payload["version"]
    assert payload["platform"]
    assert payload["uptime"] >= 0


async def test_capabilities_endpoint_is_public():
    app = create_app(_config())
    request = _build_request(app, "GET", "/capabilities")
    response = await capabilities(request)
    assert response.status == 200
    payload = json.loads(response.text)
    assert payload["platform"]
    assert "raw_shell" in payload


async def test_action_endpoint_rejects_unsigned_request():
    app = create_app(_config())
    request = _build_request(app, "POST", "/actions/run", body=b"{}")
    response = await auth_middleware(request, run_action)
    assert response.status == 401


async def test_action_endpoint_rejects_invalid_signature():
    app = create_app(_config())
    body = json.dumps({"action": "system.status", "approval_id": "fresh"}).encode()
    bad_headers = _signed_headers(
        "POST", "/actions/run", body, secret="wrong-secret"
    )
    request = _build_request(
        app, "POST", "/actions/run", body=body, extra_headers=bad_headers
    )
    response = await auth_middleware(request, run_action)
    assert response.status == 401


async def test_action_endpoint_rejects_stale_timestamp():
    app = create_app(_config())
    body = b"{}"
    signed = sign_request(
        secret=SECRET,
        method="POST",
        path="/actions/run",
        actor="march7",
        body=body,
        timestamp=str(int(time.time()) - 10_000),
        nonce="stale-nonce",
    )
    request = _build_request(
        app,
        "POST",
        "/actions/run",
        body=body,
        extra_headers=headers_from_signed(signed),
    )
    response = await auth_middleware(request, run_action)
    assert response.status == 401
    payload = json.loads(response.text)
    assert "timestamp" in payload["error"]


async def test_action_endpoint_rejects_replayed_nonce():
    app = create_app(_config())
    body = json.dumps({"action": "system.status", "approval_id": _token()}).encode()
    headers = _signed_headers("POST", "/actions/run", body)

    req1 = _build_request(
        app, "POST", "/actions/run", body=body, extra_headers=headers
    )
    resp1 = await auth_middleware(req1, run_action)
    assert resp1.status == 200

    # Same signed headers => same transport nonce => replayed at the auth layer.
    req2 = _build_request(
        app, "POST", "/actions/run", body=body, extra_headers=headers
    )
    resp2 = await auth_middleware(req2, run_action)
    assert resp2.status == 401
    payload = json.loads(resp2.text)
    assert "nonce" in payload["error"]


async def test_action_endpoint_denies_missing_approval_id():
    app = create_app(_config())
    body = json.dumps({"action": "system.status"}).encode()
    headers = _signed_headers("POST", "/actions/run", body)
    request = _build_request(
        app, "POST", "/actions/run", body=body, extra_headers=headers
    )
    response = await auth_middleware(request, run_action)
    assert response.status == 403
    payload = json.loads(response.text)
    assert payload["error"] == "approval_required"


async def test_action_endpoint_denies_replayed_approval_id():
    app = create_app(_config())
    token = _token()
    body = json.dumps({"action": "system.status", "approval_id": token}).encode()
    headers1 = _signed_headers("POST", "/actions/run", body)
    req1 = _build_request(
        app, "POST", "/actions/run", body=body, extra_headers=headers1
    )
    resp1 = await auth_middleware(req1, run_action)
    assert resp1.status == 200

    # Fresh transport signature but the SAME approval token => replayed token.
    headers2 = _signed_headers("POST", "/actions/run", body)
    req2 = _build_request(
        app, "POST", "/actions/run", body=body, extra_headers=headers2
    )
    resp2 = await auth_middleware(req2, run_action)
    assert resp2.status == 403
    payload = json.loads(resp2.text)
    assert payload["error"] == "approval_replayed"


async def test_action_endpoint_rejects_unknown_action():
    app = create_app(_config())
    body = json.dumps({
        "action": "system.unknown_action",
        "approval_id": "fresh",
    }).encode()
    headers = _signed_headers("POST", "/actions/run", body)
    request = _build_request(
        app, "POST", "/actions/run", body=body, extra_headers=headers
    )
    response = await auth_middleware(request, run_action)
    assert response.status == 403
    payload = json.loads(response.text)
    assert payload["error"] == "action_not_available"


async def test_shell_endpoint_denied_by_default():
    app = create_app(_config())
    body = json.dumps({"command": "uptime", "approval_id": "fresh"}).encode()
    headers = _signed_headers("POST", "/shell/run", body)
    request = _build_request(
        app, "POST", "/shell/run", body=body, extra_headers=headers
    )
    response = await auth_middleware(request, run_shell)
    assert response.status == 403
    payload = json.loads(response.text)
    assert payload["error"] == "raw_shell_disabled"


async def test_shell_endpoint_requires_approval_when_enabled():
    app = create_app(_config(raw_shell_enabled=True))
    body = json.dumps({"command": "uptime"}).encode()
    headers = _signed_headers("POST", "/shell/run", body)
    request = _build_request(
        app, "POST", "/shell/run", body=body, extra_headers=headers
    )
    response = await auth_middleware(request, run_shell)
    assert response.status == 403
    payload = json.loads(response.text)
    assert payload["error"] == "approval_required"


async def test_shell_endpoint_acknowledges_when_enabled_and_approved():
    app = create_app(_config(raw_shell_enabled=True))
    token = _token(action="shell")
    body = json.dumps({"command": "uptime", "approval_id": token}).encode()
    headers = _signed_headers("POST", "/shell/run", body)
    request = _build_request(
        app, "POST", "/shell/run", body=body, extra_headers=headers
    )
    response = await auth_middleware(request, run_shell)
    assert response.status == 501
    payload = json.loads(response.text)
    assert payload["error"] == "shell_execution_not_implemented"


async def test_mutating_path_refuses_when_secret_unset():
    app = create_app(GatewayConfig(shared_secret=None))
    request = _build_request(app, "POST", "/actions/run", body=b"{}")
    response = await auth_middleware(request, run_action)
    assert response.status == 503


async def test_action_endpoint_executes_system_status():
    app = create_app(_config())
    token = _token()
    body = json.dumps({"action": "system.status", "approval_id": token}).encode()
    headers = _signed_headers("POST", "/actions/run", body)
    request = _build_request(
        app, "POST", "/actions/run", body=body, extra_headers=headers
    )
    response = await auth_middleware(request, run_action)
    assert response.status == 200
    payload = json.loads(response.text)
    assert payload["ok"] is True
    assert payload["output"]
    assert payload["data"]["system"]


async def test_action_endpoint_caps_timeout_to_maximum():
    app = create_app(_config())
    token = _token()
    body = json.dumps({
        "action": "system.status",
        "approval_id": token,
        "timeout": 99_999,
    }).encode()
    headers = _signed_headers("POST", "/actions/run", body)
    request = _build_request(
        app, "POST", "/actions/run", body=body, extra_headers=headers
    )
    response = await auth_middleware(request, run_action)
    # Oversized timeout is clamped, the action still executes successfully.
    assert response.status == 200
    started = [
        event for event in app[STATE_KEY].audit_log
        if event.get("event") == "action.started"
    ]
    assert started[-1]["details"]["timeout"] == 300


async def test_action_endpoint_rejects_missing_token():
    app = create_app(_config())
    body = json.dumps({"action": "system.status"}).encode()
    headers = _signed_headers("POST", "/actions/run", body)
    request = _build_request(
        app, "POST", "/actions/run", body=body, extra_headers=headers
    )
    response = await auth_middleware(request, run_action)
    assert response.status == 403
    assert json.loads(response.text)["error"] == "approval_required"


async def test_action_endpoint_rejects_forged_token():
    app = create_app(_config())
    forged = _token(secret="wrong-secret")
    body = json.dumps({"action": "system.status", "approval_id": forged}).encode()
    headers = _signed_headers("POST", "/actions/run", body)
    request = _build_request(
        app, "POST", "/actions/run", body=body, extra_headers=headers
    )
    response = await auth_middleware(request, run_action)
    assert response.status == 403
    assert json.loads(response.text)["error"] == "approval_invalid"


async def test_action_endpoint_rejects_expired_token():
    app = create_app(_config())
    expired = _token(ttl_seconds=120, now=time.time() - 10_000)
    body = json.dumps({"action": "system.status", "approval_id": expired}).encode()
    headers = _signed_headers("POST", "/actions/run", body)
    request = _build_request(
        app, "POST", "/actions/run", body=body, extra_headers=headers
    )
    response = await auth_middleware(request, run_action)
    assert response.status == 403
    assert json.loads(response.text)["error"] == "approval_invalid"


async def test_action_endpoint_rejects_action_mismatched_token():
    app = create_app(_config())
    # Token minted for a different action than the one requested.
    mismatched = _token(action="docker.list_containers")
    body = json.dumps({"action": "system.status", "approval_id": mismatched}).encode()
    headers = _signed_headers("POST", "/actions/run", body)
    request = _build_request(
        app, "POST", "/actions/run", body=body, extra_headers=headers
    )
    response = await auth_middleware(request, run_action)
    assert response.status == 403
    assert json.loads(response.text)["error"] == "approval_invalid"


async def test_action_endpoint_truncates_output():
    app = create_app(_config())
    token = _token()
    body = json.dumps({
        "action": "system.status",
        "approval_id": token,
        "max_output_chars": 256,
    }).encode()
    headers = _signed_headers("POST", "/actions/run", body)
    request = _build_request(
        app, "POST", "/actions/run", body=body, extra_headers=headers
    )
    response = await auth_middleware(request, run_action)
    assert response.status == 200
    output = json.loads(response.text)["output"]
    # 256 chars of content plus the truncation marker line.
    assert len(output) <= 256 + 64


async def test_action_endpoint_records_audit_event():
    app = create_app(_config())
    token = _token()
    body = json.dumps({"action": "system.status", "approval_id": token}).encode()
    headers = _signed_headers("POST", "/actions/run", body)
    request = _build_request(
        app, "POST", "/actions/run", body=body, extra_headers=headers
    )
    response = await auth_middleware(request, run_action)
    assert response.status == 200
    state = app[STATE_KEY]
    events = {event.get("event") for event in state.audit_log}
    assert "approval.resolved" in events
    assert "action.started" in events
    assert "action.completed" in events
    started = [
        event for event in state.audit_log
        if event.get("event") == "action.started"
        and event.get("subject") == "system.status"
    ]
    assert started, state.audit_log
    event = started[-1]
    assert event["actor"] == "march7"
    assert event["approval_id"] == token


async def test_health_and_capabilities_bypass_auth_middleware():
    """Health and capabilities must not require a signature."""

    app = create_app(GatewayConfig(shared_secret=None))
    request = _build_request(app, "GET", "/health")
    response = await auth_middleware(request, health)
    assert response.status == 200


async def test_action_disk_usage_returns_ok_with_data():
    """system.disk_usage returns ok=True with data containing filesystems."""
    app = create_app(_config())
    token = _token(action="system.disk_usage")
    body = json.dumps({
        "action": "system.disk_usage",
        "approval_id": token,
        "arguments": {"path": "/"},
    }).encode()
    headers = _signed_headers("POST", "/actions/run", body)
    request = _build_request(
        app, "POST", "/actions/run", body=body, extra_headers=headers
    )
    response = await auth_middleware(request, run_action)
    assert response.status == 200
    payload = json.loads(response.text)
    assert payload["ok"] is True
    assert "data" in payload
    assert "command" in payload["data"]


async def test_action_disk_usage_rejects_invalid_path():
    """system.disk_usage with invalid path returns ok=False error=invalid_path."""
    app = create_app(_config())
    token = _token(action="system.disk_usage")
    body = json.dumps({
        "action": "system.disk_usage",
        "approval_id": token,
        "arguments": {"path": ";rm -rf /"},
    }).encode()
    headers = _signed_headers("POST", "/actions/run", body)
    request = _build_request(
        app, "POST", "/actions/run", body=body, extra_headers=headers
    )
    response = await auth_middleware(request, run_action)
    # Validation failure in adapter returns ok=False, which the server maps to 500.
    assert response.status == 500
    payload = json.loads(response.text)
    assert payload["ok"] is False
    assert payload["error"] == "invalid_path"


async def test_action_docker_list_containers():
    """docker.list_containers returns ok; if docker unavailable, expect docker_not_available."""
    app = create_app(_config())
    token = _token(action="docker.list_containers")
    body = json.dumps({
        "action": "docker.list_containers",
        "approval_id": token,
        "arguments": {"all": False},
    }).encode()
    headers = _signed_headers("POST", "/actions/run", body)
    request = _build_request(
        app, "POST", "/actions/run", body=body, extra_headers=headers
    )
    response = await auth_middleware(request, run_action)
    assert response.status == 200
    payload = json.loads(response.text)
    # Docker may or may not be available in the test environment.
    if payload["ok"] is True:
        assert "data" in payload
        assert "containers" in payload["data"]
    else:
        assert payload["error"] == "docker_not_available"


async def test_action_docker_container_logs_rejects_invalid_name():
    """docker.container_logs validates name (reject ';rm -rf /' with invalid_container_name)."""
    app = create_app(_config())
    token = _token(action="docker.container_logs")
    body = json.dumps({
        "action": "docker.container_logs",
        "approval_id": token,
        "arguments": {"name_or_id": ";rm -rf /"},
    }).encode()
    headers = _signed_headers("POST", "/actions/run", body)
    request = _build_request(
        app, "POST", "/actions/run", body=body, extra_headers=headers
    )
    response = await auth_middleware(request, run_action)
    # Validation failure in adapter returns ok=False, which the server maps to 500.
    assert response.status == 500
    payload = json.loads(response.text)
    assert payload["ok"] is False
    assert payload["error"] == "invalid_container_name"


async def test_action_service_status_rejects_invalid_name():
    """service.status validates service_name (reject 'bad name' with invalid_service_name)."""
    app = create_app(_config())
    token = _token(action="service.status")
    body = json.dumps({
        "action": "service.status",
        "approval_id": token,
        "arguments": {"service_name": "bad name"},
    }).encode()
    headers = _signed_headers("POST", "/actions/run", body)
    request = _build_request(
        app, "POST", "/actions/run", body=body, extra_headers=headers
    )
    response = await auth_middleware(request, run_action)
    # Validation failure in adapter returns ok=False, which the server maps to 500.
    assert response.status == 500
    payload = json.loads(response.text)
    assert payload["ok"] is False
    assert payload["error"] == "invalid_service_name"


async def test_self_update_accepts_valid_owner_request():
    app = create_app(_config())
    token = _token(action="self.update", actor="owner-cli")
    body = json.dumps({
        "from_version": SERVICE_VERSION,
        "to_version": "0.2.0",
        "approval_id": token,
    }).encode()
    headers = _signed_headers("POST", "/self/update", body, secret=SECRET, actor="owner-cli")
    request = _build_request(
        app, "POST", "/self/update", body=body, extra_headers=headers
    )
    response = await auth_middleware(request, self_update)
    assert response.status == 200
    payload = json.loads(response.text)
    assert payload["ok"] is True
    assert "update accepted" in payload["message"]


async def test_self_update_rejects_unsigned_request():
    app = create_app(_config())
    body = json.dumps({"from_version": SERVICE_VERSION}).encode()
    request = _build_request(app, "POST", "/self/update", body=body)
    response = await auth_middleware(request, self_update)
    assert response.status == 401


async def test_self_update_rejects_version_mismatch():
    app = create_app(_config())
    token = _token(action="self.update", actor="owner-cli")
    body = json.dumps({
        "from_version": "not-the-real-version",
        "approval_id": token,
    }).encode()
    headers = _signed_headers("POST", "/self/update", body, secret=SECRET, actor="owner-cli")
    request = _build_request(
        app, "POST", "/self/update", body=body, extra_headers=headers
    )
    response = await auth_middleware(request, self_update)
    assert response.status == 409
    payload = json.loads(response.text)
    assert payload["error"] == "version_mismatch"


async def test_self_update_rejects_replayed_token():
    app = create_app(_config())
    token = _token(action="self.update", actor="owner-cli")
    body = json.dumps({
        "from_version": SERVICE_VERSION,
        "approval_id": token,
    }).encode()
    headers1 = _signed_headers("POST", "/self/update", body, secret=SECRET, actor="owner-cli")
    req1 = _build_request(
        app, "POST", "/self/update", body=body, extra_headers=headers1
    )
    resp1 = await auth_middleware(req1, self_update)
    assert resp1.status == 200

    headers2 = _signed_headers("POST", "/self/update", body, secret=SECRET, actor="owner-cli")
    req2 = _build_request(
        app, "POST", "/self/update", body=body, extra_headers=headers2
    )
    resp2 = await auth_middleware(req2, self_update)
    assert resp2.status == 403
    assert json.loads(resp2.text)["error"] == "approval_replayed"


async def test_action_replay_approval_token_for_new_actions():
    """Replay/approval token flow still works for new structured actions."""
    app = create_app(_config())
    token = _token(action="system.disk_usage")
    body = json.dumps({
        "action": "system.disk_usage",
        "approval_id": token,
        "arguments": {"path": "/"},
    }).encode()
    headers1 = _signed_headers("POST", "/actions/run", body)
    req1 = _build_request(
        app, "POST", "/actions/run", body=body, extra_headers=headers1
    )
    resp1 = await auth_middleware(req1, run_action)
    assert resp1.status == 200
    payload1 = json.loads(resp1.text)
    assert payload1["ok"] is True

    # Fresh transport signature but SAME approval token => replayed token.
    headers2 = _signed_headers("POST", "/actions/run", body)
    req2 = _build_request(
        app, "POST", "/actions/run", body=body, extra_headers=headers2
    )
    resp2 = await auth_middleware(req2, run_action)
    assert resp2.status == 403
    payload2 = json.loads(resp2.text)
    assert payload2["error"] == "approval_replayed"
