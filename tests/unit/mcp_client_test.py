import pytest

from twin.shared.tools.mcp_client import MCPClient
from twin.shared.tools.mcp_protocol import MCPResponse
from twin.shared.tools.mcp_transport import Transport


class FakeTransport(Transport):
    def __init__(self):
        self.connected = False
        self.requests = []

    async def connect(self) -> None:
        self.connected = True

    async def send_request(self, request):
        self.requests.append(request)
        if request.method == "initialize":
            return MCPResponse.success({"serverInfo": {"name": "fake"}}, request_id=request.id)
        if request.method == "notifications/initialized":
            return MCPResponse.success({}, request_id=None)
        if request.method == "tools/call":
            return MCPResponse.success(
                {"content": [{"type": "text", "text": "ok"}]},
                request_id=request.id,
            )
        return MCPResponse.success({}, request_id=request.id)

    async def close(self) -> None:
        self.connected = False

    def is_connected(self) -> bool:
        return self.connected


@pytest.mark.asyncio
async def test_initialize_connects_and_declares_no_sampling_capability():
    transport = FakeTransport()
    client = MCPClient(transport)

    result = await client.initialize()

    initialize_request = transport.requests[0]
    initialized_notification = transport.requests[1]
    assert result == {"serverInfo": {"name": "fake"}}
    assert initialize_request.method == "initialize"
    assert initialize_request.params["capabilities"] == {}
    assert "sampling" not in initialize_request.params["capabilities"]
    assert initialize_request.params["clientInfo"]["name"] == "march7"
    assert initialized_notification.method == "notifications/initialized"
    assert initialized_notification.id is None


@pytest.mark.asyncio
async def test_call_tool_initializes_once_then_calls_remote_tool():
    transport = FakeTransport()
    client = MCPClient(transport)

    result = await client.call_tool("tavily_search", {"query": "test"})

    assert result == "ok"
    assert [request.method for request in transport.requests] == [
        "initialize",
        "notifications/initialized",
        "tools/call",
    ]
    assert transport.requests[-1].params == {
        "name": "tavily_search",
        "arguments": {"query": "test"},
    }
