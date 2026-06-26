"""Tests for HostSystemTool needs_install payload."""
from __future__ import annotations

import json

import pytest

from twin.shared.tools.modules.system.host_system_tool import HostSystemTool


class FakeApprovalGate:
    def __init__(self, result=True):
        self.result = result
        self.calls = []

    async def check_approval(self, tool_name, command):
        self.calls.append((tool_name, command))
        return self.result


@pytest.mark.asyncio
async def test_needs_install_returns_json_payload_when_no_client():
    """When host_gateway_client is None, execute returns a JSON needs_install payload."""
    tool = HostSystemTool(approval_gate=FakeApprovalGate(), host_gateway_client=None)

    result = await tool.execute(mode="capabilities")

    # Result should be a JSON string with needs_install info
    data = json.loads(result)
    assert data["needs_install"] is True
    assert data["platform"] is not None
    assert data["bootstrap_command"] is not None
    assert isinstance(data["notes"], list)


@pytest.mark.asyncio
async def test_needs_install_returns_json_payload_on_gateway_unavailable(monkeypatch):
    """When gateway becomes unavailable during execute, needs_install payload is returned."""

    class FakeClient:
        shared_secret = None
        actor = "march7"

        async def capabilities(self):
            from twin.shared.system_gateway import HostGatewayUnavailableError
            raise HostGatewayUnavailableError("gateway down")

    tool = HostSystemTool(
        approval_gate=FakeApprovalGate(),
        host_gateway_client=FakeClient(),
    )

    result = await tool.execute(mode="capabilities")

    data = json.loads(result)
    assert data["needs_install"] is True
    assert "bootstrap_command" in data


@pytest.mark.asyncio
async def test_needs_install_payload_contains_platform_and_command():
    tool = HostSystemTool(approval_gate=FakeApprovalGate(), host_gateway_client=None)

    result = await tool.execute(mode="capabilities")
    data = json.loads(result)

    assert "platform" in data
    assert "bootstrap_command" in data
    assert "notes" in data
    assert isinstance(data["notes"], list)
    # bootstrap_command should be a non-empty string
    assert isinstance(data["bootstrap_command"], str)
    assert len(data["bootstrap_command"]) > 0


@pytest.mark.asyncio
async def test_needs_install_payload_is_valid_json():
    tool = HostSystemTool(approval_gate=FakeApprovalGate(), host_gateway_client=None)

    result = await tool.execute(mode="capabilities")

    # Should be valid JSON, parseable without errors
    data = json.loads(result)
    assert isinstance(data, dict)
    assert "needs_install" in data


@pytest.mark.asyncio
async def test_needs_install_called_for_all_modes_when_no_client():
    """All modes (capabilities, action, shell) return needs_install when no client."""
    tool = HostSystemTool(approval_gate=FakeApprovalGate(), host_gateway_client=None)

    for mode in ("capabilities", "action", "shell"):
        result = await tool.execute(mode=mode)
        data = json.loads(result)
        assert data["needs_install"] is True, f"mode={mode} should return needs_install"
