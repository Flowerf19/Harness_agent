"""
MCP Transport - Communication layer for MCP Client-Server.

Transport abstraction allows MCP to work with different communication methods:
- StdioTransport: In-process communication (stdin/stdout)
- HTTPTransport: HTTP-based communication via MCP Streamable HTTP
- WebSocketTransport: WebSocket communication (future)

Design Pattern: Strategy Pattern
- Transport is an abstract strategy
- Different implementations for different communication needs
- Client/Server use transport without knowing implementation details

Current Implementation:
- StdioTransport: For single-process deployment (Bot + MCP Server in same process)
- InMemoryTransport: For testing and direct in-process calls
- HTTPTransport: For network-based MCP Streamable HTTP (JSON-RPC 2.0)
"""

import logging
import asyncio
import json
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Callable, Awaitable

import aiohttp

from src.services.tools.mcp_protocol import MCPRequest, MCPResponse

logger = logging.getLogger(__name__)


class Transport(ABC):
    """
    Abstract base class for MCP transport layer.
    
    Defines the interface for communication between MCP Client and Server.
    
    Methods:
        send_request: Send request and wait for response
        close: Close the transport connection
    """
    
    @abstractmethod
    async def send_request(self, request: MCPRequest) -> MCPResponse:
        """
        Send a request and wait for response.
        
        Args:
            request: MCPRequest to send
            
        Returns:
            MCPResponse: Response from server
        """
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """
        Close the transport connection.
        """
        pass
    
    @abstractmethod
    def is_connected(self) -> bool:
        """
        Check if transport is connected.
        
        Returns:
            bool: True if connected, False otherwise
        """
        pass


class InMemoryTransport(Transport):
    """
    In-memory transport for direct in-process communication.
    
    Used when MCP Client and Server are in the same process.
    No serialization/deserialization needed.
    
    Attributes:
        server: MCPServer instance to communicate with
        connected: Whether transport is active
    
    Example:
        server = MCPServer(registry)
        transport = InMemoryTransport(server)
        
        client = MCPClient(transport)
        response = await client.list_tools()
    """
    
    def __init__(self, server):
        """
        Initialize in-memory transport with server reference.
        
        Args:
            server: MCPServer instance
        """
        self.server = server
        self._connected = True
        logger.info("InMemoryTransport initialized (direct server connection)")
    
    async def send_request(self, request: MCPRequest) -> MCPResponse:
        """
        Send request directly to server (no serialization).
        
        Args:
            request: MCPRequest object
            
        Returns:
            MCPResponse: Response from server
        """
        if not self._connected:
            raise RuntimeError("Transport is not connected")
        
        logger.debug(f"InMemoryTransport: Sending {request.method}")
        response = await self.server.handle_request(request)
        logger.debug(f"InMemoryTransport: Received response for {request.method}")
        
        return response
    
    async def close(self) -> None:
        """
        Close the transport (mark as disconnected).
        """
        self._connected = False
        logger.info("InMemoryTransport closed")
    
    def is_connected(self) -> bool:
        """
        Check if transport is connected.
        
        Returns:
            bool: True if connected
        """
        return self._connected
    
    def __repr__(self) -> str:
        return f"<InMemoryTransport: connected={self._connected}>"


class StdioTransport(Transport):
    """
    Stdio transport for process-based communication.
    
    Used when MCP Server runs as a separate process.
    Communication via stdin/stdout using JSON-RPC messages.
    
    Note: Currently a placeholder for future implementation.
    For now, use InMemoryTransport for in-process communication.
    
    Future Implementation:
        - Start MCP Server as subprocess
        - Write JSON requests to stdin
        - Read JSON responses from stdout
        - Handle process lifecycle
    """
    
    def __init__(self, server_command: Optional[str] = None):
        """
        Initialize stdio transport.
        
        Args:
            server_command: Command to start MCP Server subprocess
        """
        self.server_command = server_command
        self._process: Optional[asyncio.subprocess.Process] = None
        self._connected = False
        
        logger.info(f"StdioTransport initialized (command={server_command})")
        logger.warning("StdioTransport is not fully implemented. Use InMemoryTransport for now.")
    
    async def start_server(self) -> None:
        """
        Start MCP Server subprocess.
        
        Future implementation.
        """
        if self.server_command is None:
            raise RuntimeError("No server command specified")
        
        # TODO: Implement subprocess startup
        # self._process = await asyncio.create_subprocess_exec(
        #     *self.server_command.split(),
        #     stdin=asyncio.subprocess.PIPE,
        #     stdout=asyncio.subprocess.PIPE,
        # )
        # self._connected = True
        raise NotImplementedError("StdioTransport subprocess mode not implemented")
    
    async def send_request(self, request: MCPRequest) -> MCPResponse:
        """
        Send request via stdin and read response from stdout.
        
        Future implementation.
        """
        if not self._connected or self._process is None:
            raise RuntimeError("Transport is not connected")
        
        # TODO: Implement stdin/stdout communication
        # json_request = request.to_json()
        # self._process.stdin.write(json_request.encode() + b"\n")
        # await self._process.stdin.drain()
        # 
        # json_response = await self._process.stdout.readline()
        # return MCPResponse.from_json(json_response.decode())
        raise NotImplementedError("StdioTransport subprocess mode not implemented")
    
    async def close(self) -> None:
        """
        Close subprocess connection.
        """
        if self._process:
            self._process.terminate()
            await self._process.wait()
        
        self._connected = False
        logger.info("StdioTransport closed")
    
    def is_connected(self) -> bool:
        """
        Check if transport is connected.
        
        Returns:
            bool: True if subprocess is running
        """
        return self._connected and self._process is not None
    
    def __repr__(self) -> str:
        return f"<StdioTransport: connected={self._connected}, command={self.server_command}>"


class HTTPTransport(Transport):
    """
    HTTP transport for network-based communication via MCP Streamable HTTP.

    Implements the MCP Streamable HTTP transport specification:
    - Client POST JSON-RPC to server endpoint
    - Server returns Mcp-Session-Id header on initialize
    - All subsequent requests include Mcp-Session-Id header
    - Uses aiohttp for async HTTP communication

    Used when MCP Server runs as a remote HTTP service (e.g., on host machine).
    Typical URL: http://host.docker.internal:8374/mcp

    Attributes:
        server_url: URL of MCP server endpoint
        timeout: Request timeout in seconds
        _session: aiohttp ClientSession (lazy-initialized)
        _mcp_session_id: Mcp-Session-Id from server (after initialize)
        _connected: Whether transport is considered connected

    Example:
        transport = HTTPTransport("http://host.docker.internal:8374/mcp")
        await transport.connect()
        response = await transport.send_request(mcp_request)
    """

    # MCP protocol headers
    MCP_SESSION_ID_HEADER = "Mcp-Session-Id"
    MCP_PROTOCOL_VERSION_HEADER = "MCP-Protocol-Version"
    MCP_PROTOCOL_VERSION = "2024-11-05"

    def __init__(self, server_url: str, timeout: int = 30):
        """
        Initialize HTTP transport.

        Args:
            server_url: URL of MCP server endpoint
                        (e.g., "http://localhost:8374/mcp" or
                        "http://host.docker.internal:8374/mcp")
            timeout: Request timeout in seconds (default: 30)
        """
        self.server_url = server_url
        self.timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None
        self._mcp_session_id: Optional[str] = None
        self._connected = False

        logger.info(f"HTTPTransport initialized (url={server_url}, timeout={timeout}s)")

    async def connect(self) -> None:
        """
        Establish HTTP connection by creating aiohttp session.

        Does NOT send an initialize request — that's the MCPClient's job.
        This just prepares the HTTP client for communication.
        """
        if self._session and not self._session.closed:
            logger.debug("HTTPTransport: session already exists")
            return

        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
            self._connected = True
            logger.info(f"✅ HTTP Transport connected to {self.server_url}")
        except Exception as e:
            logger.error(f"Failed to create HTTP session: {e}")
            self._connected = False
            raise ConnectionError(f"Failed to connect to MCP server: {e}") from e

    async def _get_session(self) -> aiohttp.ClientSession:
        """
        Get or create aiohttp session (lazy initialization).

        Returns:
            aiohttp.ClientSession: HTTP client session
        """
        if self._session is None or self._session.closed:
            await self.connect()
        return self._session

    def _set_mcp_session_id(self, session_id: str) -> None:
        """
        Store Mcp-Session-Id received from server.

        Called after initialize response contains the session ID header.

        Args:
            session_id: Session ID from server response
        """
        self._mcp_session_id = session_id
        logger.debug(f"MCP Session ID stored: {session_id}")

    def _build_request_headers(self) -> Dict[str, str]:
        """
        Build HTTP headers for a JSON-RPC request.

        Includes Mcp-Session-Id if we have one from a previous initialize.

        Returns:
            Dict: HTTP headers for the request
        """
        headers = {
            "Content-Type": "application/json",
        }
        if self._mcp_session_id:
            headers[self.MCP_SESSION_ID_HEADER] = self._mcp_session_id
        headers[self.MCP_PROTOCOL_VERSION_HEADER] = self.MCP_PROTOCOL_VERSION
        return headers

    async def send_request(self, request: MCPRequest) -> MCPResponse:
        """
        Send JSON-RPC request to MCP server via HTTP POST.

        POSTs the request as JSON, parses the response, and handles
        Mcp-Session-Id header extraction.

        Args:
            request: MCPRequest to send

        Returns:
            MCPResponse: Parsed response from server

        Raises:
            RuntimeError: If transport is not connected
            ConnectionError: If server is unreachable
            TimeoutError: If request times out
            ValueError: If response is invalid JSON
        """
        if not self._connected:
            raise RuntimeError("HTTPTransport is not connected. Call connect() first.")

        session = await self._get_session()
        headers = self._build_request_headers()
        request_dict = request.to_dict()

        logger.debug(
            f"HTTPTransport: POST {self.server_url} | "
            f"method={request.method} | id={request.id}"
        )

        try:
            async with session.post(
                self.server_url,
                json=request_dict,
                headers=headers,
            ) as response:
                # Extract Mcp-Session-Id from response headers (case-insensitive in aiohttp)
                new_session_id = response.headers.get(self.MCP_SESSION_ID_HEADER)
                if new_session_id:
                    self._set_mcp_session_id(new_session_id)

                # Handle HTTP error statuses
                if response.status == 401:
                    raise ConnectionError("MCP server rejected authentication (HTTP 401)")
                elif response.status == 403:
                    raise ConnectionError("MCP server forbidden access (HTTP 403)")
                elif response.status == 500:
                    raise ConnectionError("MCP server internal error (HTTP 500)")
                elif response.status >= 400:
                    error_text = await response.text()
                    raise ConnectionError(
                        f"MCP server returned HTTP {response.status}: {error_text}"
                    )

                # Parse JSON response
                try:
                    response_data = await response.json()
                except (aiohttp.ContentTypeError, json.JSONDecodeError) as e:
                    raw_text = await response.text()
                    raise ValueError(
                        f"Invalid JSON response from MCP server: {raw_text[:200]}"
                    ) from e

                # Parse into MCPResponse object
                mcp_response = MCPResponse.from_dict(response_data)
                logger.debug(
                    f"HTTPTransport: Response received | "
                    f"success={mcp_response.is_success()} | id={mcp_response.id}"
                )
                return mcp_response

        except asyncio.TimeoutError:
            logger.warning(f"HTTPTransport: Request timed out after {self.timeout}s")
            raise TimeoutError(
                f"MCP server request timed out after {self.timeout}s"
            )
        except aiohttp.ClientConnectionError as e:
            logger.error(f"HTTPTransport: Connection refused — {e}")
            raise ConnectionError(f"Cannot connect to MCP server: {e}") from e
        except aiohttp.ClientError as e:
            logger.error(f"HTTPTransport: HTTP client error — {e}")
            raise ConnectionError(f"MCP server communication failed: {e}") from e

    async def close(self) -> None:
        """
        Close HTTP connection and cleanup aiohttp session.
        """
        if self._session and not self._session.closed:
            await self._session.close()
            logger.info("HTTPTransport: aiohttp session closed")

        self._session = None
        self._mcp_session_id = None
        self._connected = False
        logger.info("HTTPTransport closed")

    def is_connected(self) -> bool:
        """
        Check if transport is connected.

        Returns:
            bool: True if aiohttp session exists and is not closed
        """
        return (
            self._connected
            and self._session is not None
            and not self._session.closed
        )

    def __repr__(self) -> str:
        session_id = f", session={self._mcp_session_id[:8]}..." if self._mcp_session_id else ""
        return (
            f"<HTTPTransport: connected={self._connected}, "
            f"url={self.server_url}{session_id}>"
        )


# ==========================================
# TRANSPORT FACTORY
# ==========================================

def create_transport(transport_type: str = "inmemory", **kwargs) -> Transport:
    """
    Factory function to create transport instances.
    
    Args:
        transport_type: Type of transport ("inmemory", "stdio", "http")
        **kwargs: Transport-specific arguments
        
    Returns:
        Transport: Transport instance
        
    Raises:
        ValueError: If unknown transport type
    """
    transports = {
        "inmemory": InMemoryTransport,
        "stdio": StdioTransport,
        "http": HTTPTransport,
    }
    
    if transport_type not in transports:
        raise ValueError(f"Unknown transport type: {transport_type}")
    
    transport_class = transports[transport_type]
    return transport_class(**kwargs)