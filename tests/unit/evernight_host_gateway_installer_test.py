"""Tests for Evernight-side Host Gateway bootstrap helpers."""
from __future__ import annotations

import json

import pytest

from twin.evernight.host_gateway.installer import (
    build_bootstrap_hint,
    InstallerCoordinator,
)


def test_bootstrap_hint_uses_placeholder_when_repo_root_unset(monkeypatch):
    monkeypatch.delenv("SYSTEM_GATEWAY_BOOTSTRAP_REPO_ROOT", raising=False)

    hint = build_bootstrap_hint("linux")

    assert hint.platform == "linux"
    # Hint is now a single bootstrap-script call instead of 9 separate commands.
    assert "cd /path/to/march7" in hint.command
    assert "Thay `/path/to/march7`" in hint.render_for_chat()
    assert "scripts/bootstrap_system_gateway.py" in hint.command
    assert "python3 scripts/bootstrap_system_gateway.py" in hint.command
    assert "sudo" not in hint.command
    # Per-OS variant sanity checks.
    mac_hint = build_bootstrap_hint("macos")
    assert "python3 scripts/bootstrap_system_gateway.py" in mac_hint.command
    assert "sudo" not in mac_hint.command
    win_hint = build_bootstrap_hint("windows")
    assert "python scripts/bootstrap_system_gateway.py" in win_hint.command
    # Old manual commands must NOT leak into the simplified hint.
    assert "venv" not in hint.command
    assert "pip install" not in hint.command
    assert "systemctl restart" not in hint.command
    assert "curl -sf" not in hint.command


def test_bootstrap_hint_uses_placeholder_when_configured_root_is_not_visible(monkeypatch):
    monkeypatch.setenv("SYSTEM_GATEWAY_BOOTSTRAP_REPO_ROOT", "/repo with space")

    hint = build_bootstrap_hint("linux")

    assert "cd /path/to/march7" in hint.command
    assert "/repo with space" not in hint.command


def test_bootstrap_hint_uses_verified_repo_root(monkeypatch, tmp_path):
    repo = tmp_path / "repo with space"
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "bootstrap_system_gateway.py").write_text("", encoding="utf-8")
    (repo / "services" / "system_gateway").mkdir(parents=True)
    monkeypatch.setenv("SYSTEM_GATEWAY_BOOTSTRAP_REPO_ROOT", str(repo))

    hint = build_bootstrap_hint("linux")

    assert f"cd {repo!s}" not in hint.command
    assert f"cd '{repo!s}'" in hint.command
    assert "Repo root đã được verify" in hint.render_for_chat()


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
        "twin.evernight.host_gateway.installer.aiohttp.ClientSession",
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
