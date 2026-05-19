"""
Unit tests for HTTPTransport (MCP Streamable HTTP).

Tests cover:
- Connection lifecycle (connect, close, is_connected)
- Session ID management (Mcp-Session-Id header)
- Request/response handling (JSON-RPC POST)
- Error handling (connection refused, timeout, HTTP errors, invalid JSON)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio
import json
import aiohttp

from twin.shared.tools.mcp_transport import HTTPTransport
from twin.shared.tools.mcp_protocol import MCPRequest, MCPResponse


def _make_mock_response(status=200, headers=None, json_data=None, text_data=""):
    """Helper: create a proper mock for aiohttp response context manager."""
    mock_resp = AsyncMock()
    mock_resp.status = status
    mock_resp.headers = headers or {}
    mock_resp.text = AsyncMock(return_value=text_data)
    if json_data is not None:
        mock_resp.json = AsyncMock(return_value=json_data)
    else:
        mock_resp.json = AsyncMock(side_effect=json.JSONDecodeError("bad", "", 0))

    # Create context manager wrapper
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=mock_resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _make_mock_session(post_return):
    """Helper: create a mock aiohttp session with proper closed attribute."""
    mock_session = MagicMock()
    # Must be a plain bool, not AsyncMock, for `if self._session.closed` check
    mock_session.closed = False
    mock_session.post = MagicMock(return_value=post_return)
    mock_session.close = AsyncMock()
    return mock_session


@pytest.fixture
def transport():
    """Create HTTPTransport instance for testing."""
    return HTTPTransport("http://localhost:8374/mcp", timeout=30)


@pytest.fixture
def sample_request():
    """Create a sample MCPRequest."""
    return MCPRequest(method="tools/list", id="test-123")


@pytest.fixture
def sample_success_response():
    """Create a sample success MCPResponse dict."""
    return {
        "jsonrpc": "2.0",
        "result": {"tools": [], "count": 0},
        "id": "test-123"
    }


# ============================================================
# Connection Lifecycle Tests
# ============================================================

class TestHTTPTransportLifecycle:
    """Test connection lifecycle management."""

    @pytest.mark.asyncio
    async def test_initial_state_not_connected(self, transport):
        """Transport starts in disconnected state."""
        assert transport.is_connected() is False
        assert transport._session is None
        assert transport._mcp_session_id is None

    @pytest.mark.asyncio
    async def test_connect_creates_session(self, transport):
        """Connect creates aiohttp session."""
        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_session = MagicMock()
            mock_session.closed = False
            mock_session.close = AsyncMock()
            mock_session_cls.return_value = mock_session

            await transport.connect()

            assert transport.is_connected() is True
            assert transport._session is mock_session
            mock_session_cls.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_idempotent(self, transport):
        """Calling connect twice doesn't create duplicate sessions."""
        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_session = MagicMock()
            mock_session.closed = False
            mock_session.close = AsyncMock()
            mock_session_cls.return_value = mock_session

            await transport.connect()
            await transport.connect()

            # Should only create session once
            assert mock_session_cls.call_count == 1

    @pytest.mark.asyncio
    async def test_close_session(self, transport):
        """Close shuts down session and clears state."""
        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_session = MagicMock()
            mock_session.closed = False
            mock_session.close = AsyncMock()
            mock_session_cls.return_value = mock_session

            await transport.connect()
            assert transport.is_connected() is True

            await transport.close()
            assert transport.is_connected() is False
            assert transport._session is None
            assert transport._mcp_session_id is None
            mock_session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_without_session(self, transport):
        """Close on uninitialized transport doesn't crash."""
        await transport.close()  # Should not raise
        assert transport.is_connected() is False

    @pytest.mark.asyncio
    async def test_is_connected_false_when_session_closed(self, transport):
        """is_connected returns False when underlying session is closed."""
        mock_session = MagicMock()
        mock_session.closed = True  # Session exists but closed
        transport._session = mock_session
        transport._connected = True

        assert transport.is_connected() is False


# ============================================================
# Session ID Management Tests
# ============================================================

class TestSessionIdManagement:
    """Test Mcp-Session-Id header handling."""

    @pytest.mark.asyncio
    async def test_session_id_stored(self, transport):
        """Session ID is stored when set."""
        transport._connected = True
        transport._set_mcp_session_id("session-abc-123")
        assert transport._mcp_session_id == "session-abc-123"

    @pytest.mark.asyncio
    async def test_headers_without_session_id(self, transport):
        """Headers don't include Mcp-Session-Id when not set."""
        transport._mcp_session_id = None
        headers = transport._build_request_headers()

        assert "Mcp-Session-Id" not in headers
        assert headers["Content-Type"] == "application/json"
        assert headers["MCP-Protocol-Version"] == "2024-11-05"

    @pytest.mark.asyncio
    async def test_headers_with_session_id(self, transport):
        """Headers include Mcp-Session-Id when set."""
        transport._mcp_session_id = "session-abc-123"
        headers = transport._build_request_headers()

        assert headers["Mcp-Session-Id"] == "session-abc-123"


# ============================================================
# Request/Response Tests
# ============================================================

class TestSendRequest:
    """Test JSON-RPC request sending and response parsing."""

    @pytest.mark.asyncio
    async def test_send_request_success(self, transport, sample_request, sample_success_response):
        """Successful request returns parsed MCPResponse."""
        cm = _make_mock_response(
            status=200,
            headers={},
            json_data=sample_success_response,
        )
        mock_session = _make_mock_session(post_return=cm)

        transport._session = mock_session
        transport._connected = True

        result = await transport.send_request(sample_request)

        assert isinstance(result, MCPResponse)
        assert result.is_success() is True
        assert result.id == "test-123"
        # Verify POST was called with correct args
        mock_session.post.assert_called_once()
        call_kwargs = mock_session.post.call_args[1]
        assert call_kwargs["json"]["method"] == "tools/list"

    @pytest.mark.asyncio
    async def test_send_request_with_session_id_in_response(self, transport, sample_request, sample_success_response):
        """Session ID from response header is stored."""
        cm = _make_mock_response(
            status=200,
            headers={"Mcp-Session-Id": "new-session-xyz"},
            json_data=sample_success_response,
        )
        mock_session = _make_mock_session(post_return=cm)

        transport._session = mock_session
        transport._connected = True

        await transport.send_request(sample_request)

        assert transport._mcp_session_id == "new-session-xyz"

    @pytest.mark.asyncio
    async def test_send_request_not_connected_raises(self, transport, sample_request):
        """Sending request when not connected raises RuntimeError."""
        with pytest.raises(RuntimeError, match="not connected"):
            await transport.send_request(sample_request)

    @pytest.mark.asyncio
    async def test_send_request_includes_session_id_when_set(self, transport, sample_request, sample_success_response):
        """Request headers include Mcp-Session-Id when previously stored."""
        cm = _make_mock_response(
            status=200,
            headers={},
            json_data=sample_success_response,
        )
        mock_session = _make_mock_session(post_return=cm)

        transport._session = mock_session
        transport._connected = True
        transport._mcp_session_id = "existing-session"

        await transport.send_request(sample_request)

        _, call_kwargs = mock_session.post.call_args
        assert call_kwargs["headers"]["Mcp-Session-Id"] == "existing-session"


# ============================================================
# Error Handling Tests
# ============================================================

class TestErrorHandling:
    """Test error scenarios."""

    @pytest.mark.asyncio
    async def test_http_401_raises_connection_error(self, transport, sample_request):
        """HTTP 401 raises ConnectionError."""
        cm = _make_mock_response(status=401)
        mock_session = _make_mock_session(post_return=cm)

        transport._session = mock_session
        transport._connected = True

        with pytest.raises(ConnectionError, match="401"):
            await transport.send_request(sample_request)

    @pytest.mark.asyncio
    async def test_http_403_raises_connection_error(self, transport, sample_request):
        """HTTP 403 raises ConnectionError."""
        cm = _make_mock_response(status=403)
        mock_session = _make_mock_session(post_return=cm)

        transport._session = mock_session
        transport._connected = True

        with pytest.raises(ConnectionError, match="403"):
            await transport.send_request(sample_request)

    @pytest.mark.asyncio
    async def test_http_500_raises_connection_error(self, transport, sample_request):
        """HTTP 500 raises ConnectionError."""
        cm = _make_mock_response(status=500)
        mock_session = _make_mock_session(post_return=cm)

        transport._session = mock_session
        transport._connected = True

        with pytest.raises(ConnectionError, match="500"):
            await transport.send_request(sample_request)

    @pytest.mark.asyncio
    async def test_http_4xx_raises_connection_error(self, transport, sample_request):
        """HTTP 4xx (other than 401/403) raises ConnectionError."""
        cm = _make_mock_response(status=404, text_data="Not found")
        mock_session = _make_mock_session(post_return=cm)

        transport._session = mock_session
        transport._connected = True

        with pytest.raises(ConnectionError, match="404"):
            await transport.send_request(sample_request)

    @pytest.mark.asyncio
    async def test_invalid_json_raises_value_error(self, transport, sample_request):
        """Invalid JSON response raises ValueError."""
        cm = _make_mock_response(
            status=200,
            headers={},
            text_data="bad json response",
        )
        mock_session = _make_mock_session(post_return=cm)

        transport._session = mock_session
        transport._connected = True

        with pytest.raises(ValueError, match="Invalid JSON"):
            await transport.send_request(sample_request)

    @pytest.mark.asyncio
    async def test_connection_refused_raises_connection_error(self, transport, sample_request):
        """Connection refused raises ConnectionError."""
        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.post = MagicMock(
            side_effect=aiohttp.ClientConnectionError("Connection refused")
        )

        transport._session = mock_session
        transport._connected = True

        with pytest.raises(ConnectionError, match="Cannot connect"):
            await transport.send_request(sample_request)


# ============================================================
# Integration-style Test (mocked HTTP)
# ============================================================

class TestEndToEnd:
    """End-to-end style test with mocked HTTP server."""

    @pytest.mark.asyncio
    async def test_full_flow_connect_send_close(self):
        """Full lifecycle: connect -> send request -> receive response -> close."""
        # Create mock response
        cm = _make_mock_response(
            status=200,
            headers={"Mcp-Session-Id": "session-123"},
            json_data={
                "jsonrpc": "2.0",
                "result": {"tools": [{"name": "test_tool"}]},
                "id": "req-1"
            },
        )

        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.close = AsyncMock()
        mock_session.post = MagicMock(return_value=cm)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            transport = HTTPTransport("http://localhost:8374/mcp", timeout=30)

            # Connect
            await transport.connect()
            assert transport.is_connected() is True

            # Send request
            request = MCPRequest(method="tools/list", id="req-1")
            response = await transport.send_request(request)

            assert response.is_success() is True
            assert response.result == {"tools": [{"name": "test_tool"}]}
            assert transport._mcp_session_id == "session-123"

            # Close
            await transport.close()
            assert transport.is_connected() is False
            mock_session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_lazy_session_reconnect_after_close(self, transport, sample_request, sample_success_response):
        """After close, next send_request re-creates session via _get_session."""
        cm = _make_mock_response(
            status=200,
            headers={},
            json_data=sample_success_response,
        )

        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.close = AsyncMock()
        mock_session.post = MagicMock(return_value=cm)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            transport = HTTPTransport("http://localhost:8374/mcp", timeout=30)

            # Connect, then close
            await transport.connect()
            assert transport.is_connected() is True
            await transport.close()
            assert transport.is_connected() is False

            # _get_session should re-create session
            session = await transport._get_session()
            assert session is mock_session
            assert transport.is_connected() is True
