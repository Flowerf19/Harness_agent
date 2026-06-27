import pytest

from twin.shared.system_gateway import (
    GatewayActionResponse,
    GatewayCapabilities,
    verify_approval_token,
)
from twin.shared.tools.modules.system.host_system_tool import HostSystemTool


TEST_SECRET = "tool-shared-secret"


class FakeApprovalGate:
    def __init__(self, result=True):
        self.result = result
        self.calls = []

    async def check_approval(self, tool_name, command):
        self.calls.append((tool_name, command))
        return self.result


class FakeHostGatewayClient:
    def __init__(
        self,
        *,
        capabilities=None,
        shell_response=None,
        shared_secret=TEST_SECRET,
        actor="march7",
    ):
        self.shared_secret = shared_secret
        self.actor = actor
        self._capabilities = capabilities or GatewayCapabilities(
            platform="linux",
            shells=("/bin/sh",),
            features=("generic_shell_exec",),
            raw_shell=True,
        )
        self._shell_response = shell_response or GatewayActionResponse(
            ok=True,
            output="shell ok",
        )
        self.shell_calls = []

    async def capabilities(self):
        return self._capabilities

    async def run_shell(self, request):
        self.shell_calls.append(request)
        return self._shell_response


@pytest.mark.asyncio
async def test_host_system_no_gateway_returns_needs_install():
    tool = HostSystemTool(approval_gate=FakeApprovalGate(), host_gateway_client=None)

    result = await tool.execute(mode="capabilities")

    assert '"needs_install": true' in result
    assert "bootstrap_command" in result
    assert "platform" in result


@pytest.mark.asyncio
async def test_capabilities_does_not_request_approval():
    approval = FakeApprovalGate()
    client = FakeHostGatewayClient()
    tool = HostSystemTool(approval_gate=approval, host_gateway_client=client)

    result = await tool.execute(mode="capabilities")

    assert "Platform: linux" in result
    assert "Shells: /bin/sh" in result
    assert approval.calls == []


@pytest.mark.asyncio
async def test_shell_requires_approval_before_gateway_call():
    approval = FakeApprovalGate(result=True)
    client = FakeHostGatewayClient()
    tool = HostSystemTool(approval_gate=approval, host_gateway_client=client)

    result = await tool.execute(mode="shell", command="uptime")

    assert "shell ok" in result
    assert approval.calls[0] == ("host_system", "host shell: uptime")
    assert client.shell_calls[0].command == "uptime"
    # A valid action-bound token (action="shell") is minted and attached.
    token = client.shell_calls[0].approval_id
    assert token
    result_token = verify_approval_token(
        secret=TEST_SECRET, token=token, action="shell", actor="march7"
    )
    assert result_token.valid is True


@pytest.mark.asyncio
async def test_shell_without_shared_secret_is_blocked():
    approval = FakeApprovalGate(result=True)
    client = FakeHostGatewayClient(shared_secret=None)
    tool = HostSystemTool(approval_gate=approval, host_gateway_client=client)

    result = await tool.execute(mode="shell", command="uptime")

    assert "shared secret" in result
    assert client.shell_calls == []


@pytest.mark.asyncio
async def test_rejected_shell_does_not_call_gateway():
    approval = FakeApprovalGate(result=False)
    client = FakeHostGatewayClient()
    tool = HostSystemTool(approval_gate=approval, host_gateway_client=client)

    result = await tool.execute(mode="shell", command="uptime")

    assert "bị từ chối" in result
    assert client.shell_calls == []


@pytest.mark.asyncio
async def test_shell_is_denied_when_capability_disables_raw_shell():
    approval = FakeApprovalGate(result=True)
    client = FakeHostGatewayClient(
        capabilities=GatewayCapabilities(
            platform="linux",
            shells=("/bin/sh",),
            raw_shell=False,
        )
    )
    tool = HostSystemTool(approval_gate=approval, host_gateway_client=client)

    result = await tool.execute(mode="shell", command="uptime")

    assert "Shell execution" in result
    assert approval.calls == []
    assert client.shell_calls == []


@pytest.mark.asyncio
async def test_shell_requires_command():
    tool = HostSystemTool(
        approval_gate=FakeApprovalGate(), host_gateway_client=FakeHostGatewayClient()
    )

    result = await tool.execute(mode="shell", command="")

    assert "cần tham số command" in result


@pytest.mark.asyncio
async def test_mode_action_is_no_longer_supported():
    tool = HostSystemTool(
        approval_gate=FakeApprovalGate(), host_gateway_client=FakeHostGatewayClient()
    )

    result = await tool.execute(mode="action")

    assert "capabilities hoặc shell" in result