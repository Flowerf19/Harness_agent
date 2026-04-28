"""
MCP Client - Client for Model Context Protocol.

Communicates with MCP Server via Transport layer.
Provides high-level API for:
- Listing available tools
- Calling tools
- Caching tool schemas

Design:
- Transport abstraction: Works with any transport (inmemory, stdio, http)
- Schema caching: Avoid repeated tools/list calls
- Error handling: Proper error propagation

Usage:
    transport = InMemoryTransport(server)
    client = MCPClient(transport)
    
    # Get tool schemas for LLM
    schemas = await client.get_tool_schemas()
    
    # Call a tool
    result = await client.call_tool("search_memory", {"user_id": "123", "query": "test"})
"""

import logging
import asyncio
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from src.services.tools.mcp_transport import Transport, InMemoryTransport
from src.services.tools.mcp_protocol import (
    MCPRequest,
    MCPResponse,
    MCPMethods,
    ToolDefinition,
)

logger = logging.getLogger(__name__)


@dataclass
class ToolCallResult:
    """
    Result from a tool call.
    
    Attributes:
        content: Result content (text)
        is_error: Whether the call resulted in an error
        tool_name: Name of the tool that was called
    """
    
    content: str
    is_error: bool = False
    tool_name: str = ""
    
    def __str__(self) -> str:
        return self.content


class MCPClient:
    """
    Client for Model Context Protocol.
    
    High-level API for communicating with MCP Server.
    
    Attributes:
        transport: Transport layer for communication
        _cached_tools: Cached list of tools from tools/list
        _initialized: Whether client has been initialized
    
    Example:
        # Create client with in-memory transport
        server = MCPServer(registry)
        transport = InMemoryTransport(server)
        client = MCPClient(transport)
        
        # Get OpenAI schemas for LLM
        schemas = await client.get_openai_schemas()
        
        # Call a tool
        result = await client.call_tool("search_memory", {"user_id": "123", "query": "test"})
        print(result.content)
    """
    
    def __init__(self, transport: Transport, auto_initialize: bool = True):
        """
        Initialize MCP Client.
        
        Args:
            transport: Transport layer for communication
            auto_initialize: Whether to auto-initialize on first call
        """
        self.transport = transport
        self.auto_initialize = auto_initialize
        
        self._cached_tools: Optional[List[ToolDefinition]] = None
        self._initialized = False
        
        logger.info(f"MCPClient initialized with transport={type(transport).__name__}")
    
    # ==========================================
    # INITIALIZATION
    # ==========================================
    
    async def initialize(self) -> Dict[str, Any]:
        """
        Initialize connection with MCP Server.
        
        Sends initialize request to get server info and capabilities.
        
        Returns:
            Dict: Server info and capabilities
        """
        request = MCPRequest(method=MCPMethods.INITIALIZE)
        response = await self.transport.send_request(request)
        
        if response.is_success():
            self._initialized = True
            logger.info("✅ MCP Client initialized")
            return response.result or {}
        else:
            error_msg = response.error.message if response.error else "Unknown error"
            logger.error(f"❌ MCP Client initialization failed: {error_msg}")
            raise RuntimeError(f"Failed to initialize MCP Client: {error_msg}")
    
    async def ping(self) -> bool:
        """
        Ping the server to check connection.
        
        Returns:
            bool: True if server responds
        """
        request = MCPRequest(method=MCPMethods.PING)
        response = await self.transport.send_request(request)
        
        return response.is_success()
    
    # ==========================================
    # TOOL LISTING
    # ==========================================
    
    async def list_tools(self) -> List[ToolDefinition]:
        """
        Get list of available tools from server.
        
        Sends tools/list request and caches the result.
        
        Returns:
            List[ToolDefinition]: List of available tools
        """
        # Auto-initialize if needed
        if self.auto_initialize and not self._initialized:
            await self.initialize()
        
        request = MCPRequest(method=MCPMethods.TOOLS_LIST)
        response = await self.transport.send_request(request)
        
        if not response.is_success():
            error_msg = response.error.message if response.error else "Unknown error"
            logger.error(f"❌ Failed to list tools: {error_msg}")
            raise RuntimeError(f"Failed to list tools: {error_msg}")
        
        # Parse tools from response
        result = response.result or {}
        tool_dicts = result.get("tools", [])
        
        tools = [
            ToolDefinition(
                name=tool.get("name", ""),
                description=tool.get("description", ""),
                inputSchema=tool.get("inputSchema", {})
            )
            for tool in tool_dicts
        ]
        
        # Cache tools
        self._cached_tools = tools
        logger.info(f"📋 Cached {len(tools)} tools")
        
        return tools
    
    async def get_tool_schemas(self, use_cache: bool = True) -> List[ToolDefinition]:
        """
        Get tool schemas (cached or fresh).
        
        Args:
            use_cache: Whether to use cached tools (default: True)
            
        Returns:
            List[ToolDefinition]: List of tool definitions
        """
        if use_cache and self._cached_tools is not None:
            return self._cached_tools
        
        return await self.list_tools()
    
    async def get_openai_schemas(self, use_cache: bool = True) -> List[Dict[str, Any]]:
        """
        Get OpenAI-compatible tool schemas.
        
        Used by LLM services to provide tool definitions.
        
        Args:
            use_cache: Whether to use cached tools
            
        Returns:
            List[Dict]: List of OpenAI tool schemas
        """
        tools = await self.get_tool_schemas(use_cache)
        return [tool.to_openai_format() for tool in tools]
    
    async def get_mcp_schemas(self, use_cache: bool = True) -> List[Dict[str, Any]]:
        """
        Get MCP-compatible tool schemas.
        
        Args:
            use_cache: Whether to use cached tools
            
        Returns:
            List[Dict]: List of MCP tool schemas
        """
        tools = await self.get_tool_schemas(use_cache)
        return [tool.to_dict() for tool in tools]
    
    # ==========================================
    # TOOL CALLING
    # ==========================================
    
    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        timeout: Optional[float] = None,
    ) -> ToolCallResult:
        """
        Call a tool on the server.
        
        Sends tools/call request and returns result.
        
        Args:
            tool_name: Name of tool to call
            arguments: Arguments for the tool
            timeout: Optional timeout (seconds)
            
        Returns:
            ToolCallResult: Result from tool execution
        """
        # Auto-initialize if needed
        if self.auto_initialize and not self._initialized:
            await self.initialize()

        # Build request
        request = MCPRequest(
            method=MCPMethods.TOOLS_CALL,
            params={
                "name": tool_name,
                "arguments": arguments
            }
        )
        
        # Send request (with optional timeout)
        try:
            if timeout:
                response = await asyncio.wait_for(
                    self.transport.send_request(request),
                    timeout=timeout
                )
            else:
                response = await self.transport.send_request(request)
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ Tool '{tool_name}' timed out after {timeout}s")
            return ToolCallResult(
                content=f"Lỗi: Tool '{tool_name}' timed out after {timeout}s",
                is_error=True,
                tool_name=tool_name
            )
        
        # Parse response
        if response.is_success():
            result = response.result or {}
            content_list = result.get("content", [])
            
            # Extract text content
            content = ""
            for item in content_list:
                if item.get("type") == "text":
                    content = item.get("text", "")
                    break
            
            is_error = result.get("isError", False)
            
            logger.info(f"✅ Tool '{tool_name}' executed: is_error={is_error}")
            
            return ToolCallResult(
                content=content,
                is_error=is_error,
                tool_name=tool_name
            )
        else:
            error_msg = response.error.message if response.error else "Unknown error"
            logger.error(f"❌ Tool '{tool_name}' failed: {error_msg}")
            
            return ToolCallResult(
                content=f"Lỗi: {error_msg}",
                is_error=True,
                tool_name=tool_name
            )
    
    # ==========================================
    # CONVENIENCE METHODS
    # ==========================================
    
    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """
        Execute a tool and return result string.
        
        Convenience method that matches old ToolManager interface.
        
        Args:
            tool_name: Name of tool to call
            arguments: Arguments for the tool
            
        Returns:
            str: Result string (or error message)
        """
        result = await self.call_tool(tool_name, arguments)
        return result.content
    
    def clear_cache(self) -> None:
        """
        Clear cached tool schemas.
        
        Forces fresh tools/list on next call.
        """
        self._cached_tools = None
        logger.info("Tool cache cleared")
    
    async def close(self) -> None:
        """
        Close the client and transport.
        """
        await self.transport.close()
        self._initialized = False
        logger.info("MCP Client closed")
    
    def is_connected(self) -> bool:
        """
        Check if client is connected.
        
        Returns:
            bool: True if transport is connected
        """
        return self.transport.is_connected()
    
    # ==========================================
    # LEGACY COMPATIBILITY
    # ==========================================
    
    def get_native_tool_schemas(self) -> List[Dict[str, Any]]:
        """
        Legacy method for compatibility with old ToolManager.
        
        Returns cached OpenAI schemas synchronously.
        If cache is empty, returns empty list (should call list_tools first).
        
        Returns:
            List[Dict]: List of OpenAI tool schemas
        """
        if self._cached_tools is None:
            logger.warning("Tool cache is empty. Call list_tools() first.")
            return []
        
        return [tool.to_openai_format() for tool in self._cached_tools]
    
    def __repr__(self) -> str:
        return f"<MCPClient: initialized={self._initialized}, cached_tools={len(self._cached_tools or [])}>"