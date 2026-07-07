import json as jsonlib

import pytest

from twin.shared.system_gateway.auth import (
    extract_auth_headers,
    is_timestamp_within_skew,
    verify_signature,
)
from twin.shared.system_gateway.client import (
    MAX_RESPONSE_BYTES,
    HostGatewayClient,
    _loads_json,
)
from twin.shared.system_gateway.errors import HostGatewayError
from twin.shared.system_gateway.types import (
    GatewayActionResponse,
    GatewayCapabilities,
    GatewayHealth,
    GatewayShellRequest,
)


def test_gateway_health_from_dict_coerces_optional_fields():
    health = GatewayHealth.from_dict({
        "status": "ok",
        "version": "0.1.0",
        "platform": "linux",
        "uptime": "42",
    })

    assert health.status == "ok"
    assert health.version == "0.1.0"
    assert health.platform == "linux"
    assert health.uptime == 42


def test_gateway_capabilities_from_dict_defaults_to_safe_values():
    capabilities = GatewayCapabilities.from_dict({
        "platform": "windows",
        "shells": ["powershell"],
        "features": ["services"],
        "structured_actions": ["service.status"],
        "notes": ["stub"],
    })

    assert capabilities.platform == "windows"
    assert capabilities.shells == ("powershell",)
    assert capabilities.features == ("services",)
    assert capabilities.structured_actions == ("service.status",)
    assert capabilities.raw_shell is False
    assert capabilities.notes == ("stub",)


def test_gateway_action_response_accepts_legacy_stdout_shape():
    response = GatewayActionResponse.from_dict({
        "success": True,
        "stdout": "hello",
        "exit_code": "0",
    })

    assert response.ok is True
    assert response.output == "hello"
    assert response.exit_code == 0


def test_loads_json_rejects_non_object_payload():
    with pytest.raises(HostGatewayError, match="invalid JSON payload"):
        _loads_json(b"[]", 200)


def test_client_response_size_limit_constant_is_bounded():
    assert MAX_RESPONSE_BYTES <= 1_000_000


class _FakeContent:
    async def read(self, n):
        return b"x" * n


class _FakeResponse:
    status = 200

    def __init__(self):
        self.content = _FakeContent()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeSession:
    closed = False

    def request(self, method, url, *, data=None, headers=None):
        return _FakeResponse()


@pytest.mark.asyncio
async def test_request_json_rejects_oversized_response():
    client = HostGatewayClient("http://gateway.local")
    client._session = _FakeSession()

    with pytest.raises(HostGatewayError, match="exceeded size limit"):
        await client._request_json("GET", "/capabilities")


class _CapturingResponse:
    status = 200

    def __init__(self):
        class _Content:
            async def read(self, n):
                return b'{"ok": true}'

        self.content = _Content()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _CapturingSession:
    closed = False

    def __init__(self):
        self.calls = []

    def request(self, method, url, *, data=None, headers=None):
        self.calls.append({"method": method, "url": url, "data": data, "headers": headers})
        return _CapturingResponse()


@pytest.mark.asyncio
async def test_client_signs_request_with_exact_body_bytes():
    secret = "client-shared-secret"
    client = HostGatewayClient(
        "http://gateway.local", shared_secret=secret, actor="march7"
    )
    session = _CapturingSession()
    client._session = session

    await client.run_shell(
        GatewayShellRequest(command="uptime", approval_id="tok", timeout=30)
    )

    call = session.calls[-1]
    headers = extract_auth_headers(call["headers"])
    # All four auth headers attached.
    assert headers["signature"]
    assert headers["timestamp"]
    assert headers["nonce"]
    assert headers["actor"] == "march7"
    assert is_timestamp_within_skew(headers["timestamp"])
    # The signature verifies over the EXACT bytes sent on the wire.
    assert verify_signature(
        secret,
        method="POST",
        path="/shell/run",
        timestamp=headers["timestamp"],
        nonce=headers["nonce"],
        actor=headers["actor"],
        body=call["data"],
        signature=headers["signature"],
    )
    # Body is compact JSON encoded as bytes, not handed to aiohttp as json=.
    assert call["data"] == jsonlib.dumps(
        {"command": "uptime", "timeout": 30, "max_output_chars": 8000, "approval_id": "tok"},
        separators=(",", ":"),
    ).encode("utf-8")


@pytest.mark.asyncio
async def test_client_without_secret_attaches_no_auth_headers():
    client = HostGatewayClient("http://gateway.local")
    session = _CapturingSession()
    client._session = session

    await client._request_json("GET", "/health")

    headers = session.calls[-1]["headers"]
    assert "X-System-Gateway-Signature" not in headers
