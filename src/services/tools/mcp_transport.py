"""
MCP Transport - Communication layer for MCP Client-Server.

Transport abstraction allows MCP to work with different communication methods:
- StdioTransport: In-process communication (stdin/stdout)
- HTTPTransport: HTTP-based communication (future)
- WebSocketTransport: WebSocket communication (future)

Design Pattern: Strategy Pattern
- Transport is an abstract strategy
- Different implementations for different communication needs
- Client/Server use transport without knowing implementation details

Current Implementation:
- StdioTransport: For single-process deployment (Bot + MCP Server in same process)
- InMemoryTransport: For testing and direct in-process calls
"""

import logging
import asyncio
import json
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Callable, Awaitable

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
    HTTP transport for network-based communication.
    
    Used when MCP Server runs as a remote HTTP service.
    Communication via HTTP POST requests.
    
    Note: Currently a placeholder for future implementation.
    For remote MCP servers, this would be the preferred transport.
    
    Future Implementation:
        - Send JSON-RPC requests via HTTP POST
        - Handle authentication/authorization
        - Support for multiple remote servers
    """
    
    def __init__(self, server_url: str, timeout: int = 30):
        """
        Initialize HTTP transport.
        
        Args:
            server_url: URL of MCP Server (e.g., "http://localhost:8080/mcp")
            timeout: Request timeout in seconds
        """
        self.server_url = server_url
        self.timeout = timeout
        self._connected = False
        
        logger.info(f"HTTPTransport initialized (url={server_url})")
        logger.warning("HTTPTransport is not fully implemented. Use InMemoryTransport for now.")
    
    async def connect(self) -> None:
        """
        Establish HTTP connection.
        
        Future implementation.
        """
        # TODO: Implement HTTP connection setup
        # Could use aiohttp or httpx
        self._connected = True
        raise NotImplementedError("HTTPTransport not implemented")
    
    async def send_request(self, request: MCPRequest) -> MCPResponse:
        """
        Send request via HTTP POST.
        
        Future implementation.
        """
        if not self._connected:
            raise RuntimeError("Transport is not connected")
        
        # TODO: Implement HTTP POST
        # async with aiohttp.ClientSession() as session:
        #     async with session.post(
        #         self.server_url,
        #         json=request.to_dict(),
        #         timeout=self.timeout
        #     ) as response:
        #         data = await response.json()
        #         return MCPResponse.from_dict(data)
        raise NotImplementedError("HTTPTransport not implemented")
    
    async def close(self) -> None:
        """
        Close HTTP connection.
        """
        self._connected = False
        logger.info("HTTPTransport closed")
    
    def is_connected(self) -> bool:
        """
        Check if transport is connected.
        
        Returns:
            bool: True if connected
        """
        return self._connected
    
    def __repr__(self) -> str:
        return f"<HTTPTransport: connected={self._connected}, url={self.server_url}>"


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