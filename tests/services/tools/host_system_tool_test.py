import pytest

from twin.shared.system_gateway import GatewayActionResponse, GatewayCapabilities
from twin.shared.tools.modules.system.host_system_tool import HostSystemTool


class FakeApprovalGate:
    def __init__(self, result=True):
        self.result = result
        self.calls = []

    async def check_approval(self, tool_name, command):
        self.calls.append((tool_name, command))
        return self.result


class FakeHostGatewayClient:
    def __init__(self, *, capabilities=None, action_response=None, shell_response=None):
        self._capabilities = capabilities or GatewayCapabilities(
            platform="linux",
            shells=("bash",),
            features=("docker",),
            structured_actions=("system.status",),
            raw_shell=False,
        )
        self._action_response = action_response or GatewayActionResponse(
            ok=True,
            output="status ok",
        )
        self._shell_response = shell_response or GatewayActionResponse(
            ok=True,
            output="shell ok",
        )
        self.action_calls = []
        self.shell_calls = []

    async def capabilities(self):
        return self._capabilities

    async def run_action(self, request):
        self.action_calls.append(request)
        return self._action_response

    async def run_shell(self, request):
        self.shell_calls.append(request)
        return self._shell_response


@pytest.mark.asyncio
async def test_host_system_no_gateway_returns_configuration_error():
    tool = HostSystemTool(approval_gate=FakeApprovalGate(), host_gateway_client=None)

    result = await tool.execute(mode="capabilities")

    assert "System Gateway" in result
    assert "chưa được cấu hình" in result


@pytest.mark.asyncio
async def test_capabilities_does_not_request_approval():
    approval = FakeApprovalGate()
    client = FakeHostGatewayClient()
    tool = HostSystemTool(approval_gate=approval, host_gateway_client=client)

    result = await tool.execute(mode="capabilities")

    assert "Platform: linux" in result
    assert "system.status" in result
    assert approval.calls == []


@pytest.mark.asyncio
async def test_action_requires_approval_before_gateway_call():
    approval = FakeApprovalGate(result=True)
    client = FakeHostGatewayClient()
    tool = HostSystemTool(approval_gate=approval, host_gateway_client=client)

    result = await tool.execute(
        mode="action",
        action="system.status",
        arguments={"verbose": True},
    )

    assert "status ok" in result
    assert approval.calls[0][0] == "host_system"
    assert "system.status" in approval.calls[0][1]
    assert client.action_calls[0].action == "system.status"
    assert client.action_calls[0].arguments == {"verbose": True}


@pytest.mark.asyncio
async def test_unsupported_action_does_not_request_approval_or_call_gateway():
    approval = FakeApprovalGate(result=True)
    client = FakeHostGatewayClient(
        capabilities=GatewayCapabilities(
            platform="linux",
            structured_actions=(),
        )
    )
    tool = HostSystemTool(approval_gate=approval, host_gateway_client=client)

    result = await tool.execute(mode="action", action="system.status")

    assert "không hỗ trợ action" in result
    assert approval.calls == []
    assert client.action_calls == []


@pytest.mark.asyncio
async def test_rejected_action_does_not_call_gateway():
    approval = FakeApprovalGate(result=False)
    client = FakeHostGatewayClient()
    tool = HostSystemTool(approval_gate=approval, host_gateway_client=client)

    result = await tool.execute(mode="action", action="system.status")

    assert "bị từ chối" in result
    assert client.action_calls == []


@pytest.mark.asyncio
async def test_shell_is_denied_when_capability_disables_raw_shell():
    approval = FakeApprovalGate(result=True)
    client = FakeHostGatewayClient(
        capabilities=GatewayCapabilities(
            platform="linux",
            shells=("bash",),
            structured_actions=("system.status",),
            raw_shell=False,
        )
    )
    tool = HostSystemTool(approval_gate=approval, host_gateway_client=client)

    result = await tool.execute(mode="shell", command="uptime")

    assert "Raw shell" in result
    assert approval.calls == []
    assert client.shell_calls == []
