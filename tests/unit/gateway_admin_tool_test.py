"""Tests for GatewayAdminTool owner gate and command routing."""
from __future__ import annotations

import pytest

from twin.shared.tools.modules.system.gateway_admin_tool import GatewayAdminTool


class _FakeApprovalContext:
    def __init__(self, user_id: str):
        self.user_id = user_id


class _FakeGatewayMonitor:
    def __init__(self, *, version: str | None = "0.1.0", base_url: str = "http://gw"):
        self.base_url = base_url
        self.timeout = 30
        self._version = version
        self._snapshot = _FakeSnapshot(version=version)
        self.refresh_calls = 0

    @property
    def snapshot(self):
        return self._snapshot

    async def refresh_once(self):
        self.refresh_calls += 1

    def status_for_chat(self) -> str:
        return "Gateway status line"


class _FakeSnapshot:
    def __init__(self, version: str | None = "0.1.0"):
        self.version = version


class _FakeHostGatewayClient:
    def __init__(self, shared_secret: str | None = None, actor: str = "evernight"):
        self.shared_secret = shared_secret
        self.actor = actor


# ---------------------------------------------------------------------------
# Owner gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_owner_gate_rejects_non_owner(monkeypatch):
    tool = GatewayAdminTool(
        owner_user_id="owner-123",
        gateway_monitor=_FakeGatewayMonitor(),
    )

    ctx = _FakeApprovalContext(user_id="someone-else")
    monkeypatch.setattr(
        "twin.shared.tools.modules.system.gateway_admin_tool.get_current_approval_context",
        lambda: ctx,
    )

    result = await tool.execute(command="status")
    assert "❌" in result
    assert "owner" in result.lower()


@pytest.mark.asyncio
async def test_owner_gate_rejects_when_no_context(monkeypatch):
    tool = GatewayAdminTool(
        owner_user_id="owner-123",
        gateway_monitor=_FakeGatewayMonitor(),
    )

    monkeypatch.setattr(
        "twin.shared.tools.modules.system.gateway_admin_tool.get_current_approval_context",
        lambda: None,
    )

    result = await tool.execute(command="status")
    assert "❌" in result
    assert "owner" in result.lower()


@pytest.mark.asyncio
async def test_owner_gate_allows_owner(monkeypatch):
    tool = GatewayAdminTool(
        owner_user_id="owner-123",
        gateway_monitor=_FakeGatewayMonitor(),
    )

    ctx = _FakeApprovalContext(user_id="owner-123")
    monkeypatch.setattr(
        "twin.shared.tools.modules.system.gateway_admin_tool.get_current_approval_context",
        lambda: ctx,
    )

    result = await tool.execute(command="status")
    # Owner is allowed through, should get status output
    assert "❌" not in result


# ---------------------------------------------------------------------------
# Command routing: status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_returns_error_when_monitor_missing(monkeypatch):
    tool = GatewayAdminTool(
        owner_user_id="owner-123",
        gateway_monitor=None,
    )

    ctx = _FakeApprovalContext(user_id="owner-123")
    monkeypatch.setattr(
        "twin.shared.tools.modules.system.gateway_admin_tool.get_current_approval_context",
        lambda: ctx,
    )

    result = await tool.execute(command="status")
    assert "❌" in result
    assert "GatewayMonitor" in result


@pytest.mark.asyncio
async def test_status_returns_monitor_chat_status(monkeypatch):
    monitor = _FakeGatewayMonitor()
    tool = GatewayAdminTool(
        owner_user_id="owner-123",
        gateway_monitor=monitor,
    )

    ctx = _FakeApprovalContext(user_id="owner-123")
    monkeypatch.setattr(
        "twin.shared.tools.modules.system.gateway_admin_tool.get_current_approval_context",
        lambda: ctx,
    )

    result = await tool.execute(command="status")
    assert result == "Gateway status line"


# ---------------------------------------------------------------------------
# Command routing: doctor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_doctor_refreshes_monitor_and_returns_status(monkeypatch):
    monitor = _FakeGatewayMonitor()
    tool = GatewayAdminTool(
        owner_user_id="owner-123",
        gateway_monitor=monitor,
    )

    ctx = _FakeApprovalContext(user_id="owner-123")
    monkeypatch.setattr(
        "twin.shared.tools.modules.system.gateway_admin_tool.get_current_approval_context",
        lambda: ctx,
    )

    result = await tool.execute(command="doctor")
    assert monitor.refresh_calls == 1
    assert result == "Gateway status line"


# ---------------------------------------------------------------------------
# Command routing: install_hint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_install_hint_returns_bootstrap_hint(monkeypatch):
    tool = GatewayAdminTool(
        owner_user_id="owner-123",
        gateway_monitor=None,
    )

    ctx = _FakeApprovalContext(user_id="owner-123")
    monkeypatch.setattr(
        "twin.shared.tools.modules.system.gateway_admin_tool.get_current_approval_context",
        lambda: ctx,
    )

    result = await tool.execute(command="install_hint")
    assert "System Gateway bootstrap" in result
    assert "```" in result


@pytest.mark.asyncio
async def test_install_returns_manual_bootstrap_hint(monkeypatch):
    tool = GatewayAdminTool(
        owner_user_id="owner-123",
        gateway_monitor=None,
    )

    ctx = _FakeApprovalContext(user_id="owner-123")
    monkeypatch.setattr(
        "twin.shared.tools.modules.system.gateway_admin_tool.get_current_approval_context",
        lambda: ctx,
    )
    monkeypatch.setenv("SYSTEM_GATEWAY_BOOTSTRAP_REPO_ROOT", "/repo")

    result = await tool.execute(command="install")

    assert "Legacy bootstrap executor" in result
    assert "System Gateway bootstrap" in result
    assert "cd /repo" in result
    assert "127.0.0.1:8380/health" in result


@pytest.mark.asyncio
async def test_install_still_requires_owner(monkeypatch):
    tool = GatewayAdminTool(
        owner_user_id="owner-123",
    )

    ctx = _FakeApprovalContext(user_id="someone-else")
    monkeypatch.setattr(
        "twin.shared.tools.modules.system.gateway_admin_tool.get_current_approval_context",
        lambda: ctx,
    )

    result = await tool.execute(command="install")

    assert "owner" in result.lower()


# ---------------------------------------------------------------------------
# Command routing: update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_returns_error_when_monitor_missing(monkeypatch):
    tool = GatewayAdminTool(
        owner_user_id="owner-123",
        gateway_monitor=None,
    )

    ctx = _FakeApprovalContext(user_id="owner-123")
    monkeypatch.setattr(
        "twin.shared.tools.modules.system.gateway_admin_tool.get_current_approval_context",
        lambda: ctx,
    )

    result = await tool.execute(command="update")
    assert "❌" in result
    assert "GatewayMonitor" in result


@pytest.mark.asyncio
async def test_update_returns_error_when_gateway_version_unknown(monkeypatch):
    monitor = _FakeGatewayMonitor(version=None)
    tool = GatewayAdminTool(
        owner_user_id="owner-123",
        gateway_monitor=monitor,
    )

    ctx = _FakeApprovalContext(user_id="owner-123")
    monkeypatch.setattr(
        "twin.shared.tools.modules.system.gateway_admin_tool.get_current_approval_context",
        lambda: ctx,
    )

    result = await tool.execute(command="update")
    assert "❌" in result
    assert "chưa cài đặt" in result


@pytest.mark.asyncio
async def test_update_calls_installer_coordinator(monkeypatch):
    monitor = _FakeGatewayMonitor(version="0.1.0")
    client = _FakeHostGatewayClient(shared_secret="test-secret")
    tool = GatewayAdminTool(
        owner_user_id="owner-123",
        gateway_monitor=monitor,
        host_gateway_client=client,
    )

    ctx = _FakeApprovalContext(user_id="owner-123")
    monkeypatch.setattr(
        "twin.shared.tools.modules.system.gateway_admin_tool.get_current_approval_context",
        lambda: ctx,
    )

    # Patch InstallerCoordinator to avoid real network calls
    coordinator_calls = []

    class _FakeCoordinator:
        def __init__(self, base_url, timeout, shared_secret=None, actor="evernight"):
            coordinator_calls.append({
                "base_url": base_url,
                "timeout": timeout,
                "shared_secret": shared_secret,
                "actor": actor,
            })

        async def request_update(self, current_version, target_version=None, approval_id=None):
            coordinator_calls.append({
                "current_version": current_version,
                "target_version": target_version,
                "approval_id": approval_id,
            })
            return True, "update queued"

    monkeypatch.setattr(
        "twin.evernight.system_gateway.installer.InstallerCoordinator",
        _FakeCoordinator,
    )

    result = await tool.execute(command="update", target_version="0.2.0")
    assert "✅" in result
    assert "update queued" in result
    assert coordinator_calls[0]["shared_secret"] == "test-secret"
    assert coordinator_calls[0]["actor"] == "evernight"
    assert coordinator_calls[1]["current_version"] == "0.1.0"
    assert coordinator_calls[1]["target_version"] == "0.2.0"
    # approval_id was minted because client has shared_secret
    assert coordinator_calls[1]["approval_id"] is not None


@pytest.mark.asyncio
async def test_update_without_shared_secret_returns_error(monkeypatch):
    monitor = _FakeGatewayMonitor(version="0.1.0")
    client = _FakeHostGatewayClient(shared_secret=None)
    tool = GatewayAdminTool(
        owner_user_id="owner-123",
        gateway_monitor=monitor,
        host_gateway_client=client,
    )

    ctx = _FakeApprovalContext(user_id="owner-123")
    monkeypatch.setattr(
        "twin.shared.tools.modules.system.gateway_admin_tool.get_current_approval_context",
        lambda: ctx,
    )

    result = await tool.execute(command="update")

    assert "shared secret" in result


# ---------------------------------------------------------------------------
# Command routing: invalid command
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_command_returns_error(monkeypatch):
    tool = GatewayAdminTool(
        owner_user_id="owner-123",
        gateway_monitor=_FakeGatewayMonitor(),
    )

    ctx = _FakeApprovalContext(user_id="owner-123")
    monkeypatch.setattr(
        "twin.shared.tools.modules.system.gateway_admin_tool.get_current_approval_context",
        lambda: ctx,
    )

    result = await tool.execute(command="invalid_cmd")
    assert "❌" in result
    assert "không hợp lệ" in result
    assert "status" in result
    assert "doctor" in result
    assert "install_hint" in result
    assert "install" in result
    assert "update" in result
