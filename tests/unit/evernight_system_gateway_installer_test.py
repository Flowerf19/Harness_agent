"""Tests for Evernight-side System Gateway bootstrap helpers."""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

from twin.evernight.system_gateway.installer import (
    _BOOTSTRAP_ENV_PARSER,
    InstallerCoordinator,
    LegacyBashExecutorBootstrapBridge,
)


def test_legacy_bootstrap_bridge_generates_fixed_install_command():
    bridge = LegacyBashExecutorBootstrapBridge(
        executor_url="http://bash-executor:8374",
        repo_root="/repo with space",
        python_executable="/venv/bin/python",
        venv_path="/opt/system gateway/venv",
        timeout=120,
    )

    command = bridge.build_install_command()

    assert "cd '/repo with space'" in command
    assert ". ./.env" not in command
    assert "SYSTEM_GATEWAY_SHARED_SECRET missing in .env" in command
    assert "/etc/system-gateway/secret /tmp/system-gateway-bootstrap.env" in command
    assert ". /tmp/system-gateway-bootstrap.env" in command
    assert 'printf "%s" "$SYSTEM_GATEWAY_SHARED_SECRET"' not in command
    assert "/venv/bin/python -m venv --system-site-packages '/opt/system gateway/venv'" in command
    assert "pip install --upgrade pip" not in command
    assert "'/opt/system gateway/venv'/bin/python -m pip install --no-build-isolation services/system_gateway" in command
    assert "'/opt/system gateway/venv'/bin/python -m system_gateway install" in command
    assert "systemctl restart system-gateway" in command
    assert "curl -sf" in command
    assert "for _ in 1 2 3" in command
    assert "system-gateway health check failed after restart" in command


def test_bootstrap_env_parser_does_not_execute_dotenv_values(tmp_path):
    marker = tmp_path / "marker"
    env_path = tmp_path / ".env"
    secret_path = tmp_path / "secret"
    safe_env_path = tmp_path / "safe.env"
    env_path.write_text(
        "\n".join(
            [
                f'SYSTEM_GATEWAY_SHARED_SECRET="$(touch {marker})"',
                "SYSTEM_GATEWAY_HOST=0.0.0.0",
                "SYSTEM_GATEWAY_PORT=8380",
            ]
        ),
        encoding="utf-8",
    )

    subprocess.run(
        [sys.executable, "-", str(env_path), str(secret_path), str(safe_env_path)],
        input=_BOOTSTRAP_ENV_PARSER,
        text=True,
        check=True,
    )

    assert not marker.exists()
    assert secret_path.read_text(encoding="utf-8") == f"$(touch {marker})"
    safe_env = safe_env_path.read_text(encoding="utf-8")
    assert "SYSTEM_GATEWAY_HOST=0.0.0.0" in safe_env
    assert "SYSTEM_GATEWAY_PORT=8380" in safe_env
    assert "SYSTEM_GATEWAY_SHARED_SECRET" not in safe_env


@pytest.mark.asyncio
async def test_installer_coordinator_signs_self_update_request(monkeypatch):
    opened = []

    class _FakeResponse:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def json(self):
            return {"ok": True, "message": "queued"}

    class _FakeSession:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def post(self, url, data=None, headers=None):
            opened.append({"url": url, "data": data, "headers": headers or {}})
            return _FakeResponse()

    monkeypatch.setattr(
        "twin.evernight.system_gateway.installer.aiohttp.ClientSession",
        _FakeSession,
    )

    coordinator = InstallerCoordinator(
        base_url="http://gw",
        shared_secret="secret",
        actor="evernight",
    )
    ok, message = await coordinator.request_update(
        current_version="0.1.0",
        approval_id="approval",
        target_version="0.2.0",
    )

    assert ok is True
    assert message == "queued"
    assert opened[0]["url"] == "http://gw/self/update"
    assert opened[0]["headers"]["Content-Type"] == "application/json"
    assert opened[0]["headers"]["X-System-Gateway-Actor"] == "evernight"
    assert opened[0]["headers"]["X-System-Gateway-Signature"]
    assert json.loads(opened[0]["data"]) == {
        "from_version": "0.1.0",
        "to_version": "0.2.0",
        "approval_id": "approval",
    }


@pytest.mark.asyncio
async def test_installer_coordinator_refuses_unsigned_update():
    coordinator = InstallerCoordinator(base_url="http://gw", shared_secret=None)

    ok, message = await coordinator.request_update(current_version="0.1.0")

    assert ok is False
    assert "shared secret" in message
