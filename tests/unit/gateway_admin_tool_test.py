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


class _FakeApprovalGate:
    def __init__(self, approved: bool = True):
        self.approved = approved
        self.calls = []

    async def check_approval(self, tool_name: str, command: str) -> bool:
        self.calls.append((tool_name, command))
        return self.approved


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
async def test_install_runs_fixed_bootstrap_after_owner_approval(monkeypatch):
    approval_gate = _FakeApprovalGate(approved=True)
    tool = GatewayAdminTool(
        owner_user_id="owner-123",
        gateway_monitor=None,
        approval_gate=approval_gate,
        executor_url="http://bash-executor:8374",
        bootstrap_repo_root="/repo",
        bootstrap_python="/venv/bin/python",
        bootstrap_venv="/opt/test-system-gateway/venv",
    )

    ctx = _FakeApprovalContext(user_id="owner-123")
    monkeypatch.setattr(
        "twin.shared.tools.modules.system.gateway_admin_tool.get_current_approval_context",
        lambda: ctx,
    )

    bridge_calls = []

    class _FakeBridge:
        def __init__(self, **kwargs):
            bridge_calls.append(kwargs)

        def build_install_command(self):
            return "fixed bootstrap command"

        async def install(self):
            return type(
                "Result",
                (),
                {
                    "ok": True,
                    "message": "done",
                    "stdout": "healthy\nSYSTEM_GATEWAY_SHARED_SECRET=super-token",
                    "stderr": "",
                    "exit_code": 0,
                },
            )()

    monkeypatch.setattr(
        "twin.evernight.system_gateway.installer.LegacyBashExecutorBootstrapBridge",
        _FakeBridge,
    )

    result = await tool.execute(command="install")

    assert "✅" in result
    assert "healthy" in result
    assert "super-token" not in result
    assert "[redacted system gateway secret line]" in result
    assert approval_gate.calls == [
        ("gateway_admin", "system-gateway bootstrap install:\nfixed bootstrap command")
    ]
    assert bridge_calls == [
        {
            "executor_url": "http://bash-executor:8374",
            "repo_root": "/repo",
            "python_executable": "/venv/bin/python",
            "venv_path": "/opt/test-system-gateway/venv",
            "timeout": 120,
        }
    ]


@pytest.mark.asyncio
async def test_install_rejects_when_approval_denied(monkeypatch):
    approval_gate = _FakeApprovalGate(approved=False)
    tool = GatewayAdminTool(
        owner_user_id="owner-123",
        approval_gate=approval_gate,
        executor_url="http://bash-executor:8374",
        bootstrap_repo_root="/repo",
        bootstrap_python="/venv/bin/python",
    )

    ctx = _FakeApprovalContext(user_id="owner-123")
    monkeypatch.setattr(
        "twin.shared.tools.modules.system.gateway_admin_tool.get_current_approval_context",
        lambda: ctx,
    )

    class _FakeBridge:
        def __init__(self, **kwargs):
            pass

        def build_install_command(self):
            return "fixed bootstrap command"

        async def install(self):
            raise AssertionError("install should not run after rejected approval")

    monkeypatch.setattr(
        "twin.evernight.system_gateway.installer.LegacyBashExecutorBootstrapBridge",
        _FakeBridge,
    )

    result = await tool.execute(command="install")

    assert "bị từ chối" in result


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
