"""
MCP Client - Client for external MCP servers only.

System tools are called directly via ToolRegistry.execute_tool().
MCPClient is only used when connecting to external MCP servers over HTTP.
"""

import logging
import asyncio
from typing import Dict, Any, Optional

from twin.shared.tools.mcp_transport import Transport
from twin.shared.tools.mcp_protocol import (
    MCPRequest,
    MCPResponse,
    MCPMethods,
    ToolDefinition,
)

logger = logging.getLogger(__name__)


class MCPClient:
    """
    Client for external MCP servers (HTTP transport only).
    
    Used by MCPProxyTool to call tools on remote MCP servers.
    System tools use ToolRegistry directly, not this client.
    
    Example:
        transport = HTTPTransport("http://external-server:8374/mcp")
        client = MCPClient(transport)
        result = await client.call_tool("github_search", {"query": "test"})
    """
    
    def __init__(self, transport: Transport):
        self.transport = transport
        self._initialized = False
        logger.info(f"MCPClient initialized with transport={type(transport).__name__}")
    
    async def initialize(self) -> Dict[str, Any]:
        """Initialize connection with external MCP server."""
        request = MCPRequest(method=MCPMethods.INITIALIZE)
        response = await self.transport.send_request(request)
        
        if response.is_success():
            self._initialized = True
            logger.info("MCP Client initialized")
            return response.result or {}
        else:
            error_msg = response.error.message if response.error else "Unknown error"
            raise RuntimeError(f"Failed to initialize MCP Client: {error_msg}")
    
    async def list_tools(self) -> list:
        """Get list of available tools from external MCP server."""
        if not self._initialized:
            await self.initialize()
        
        request = MCPRequest(method=MCPMethods.TOOLS_LIST)
        response = await self.transport.send_request(request)
        
        if not response.is_success():
            error_msg = response.error.message if response.error else "Unknown error"
            raise RuntimeError(f"Failed to list tools: {error_msg}")
        
        result = response.result or {}
        tool_dicts = result.get("tools", [])
        
        return [
            ToolDefinition(
                name=tool.get("name", ""),
                description=tool.get("description", ""),
                inputSchema=tool.get("inputSchema", {})
            )
            for tool in tool_dicts
        ]
    
    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        timeout: Optional[float] = None,
    ) -> str:
        """
        Call a tool on the external MCP server.
        
        Returns:
            str: Result string from tool execution
        """
        if not self._initialized:
            await self.initialize()

        request = MCPRequest(
            method=MCPMethods.TOOLS_CALL,
            params={
                "name": tool_name,
                "arguments": arguments
            }
        )
        
        try:
            if timeout:
                response = await asyncio.wait_for(
                    self.transport.send_request(request),
                    timeout=timeout
                )
            else:
                response = await self.transport.send_request(request)
        except asyncio.TimeoutError:
            logger.warning(f"Tool '{tool_name}' timed out after {timeout}s")
            return f"Lỗi: Tool '{tool_name}' timed out after {timeout}s"
        
        if response.is_success():
            result = response.result or {}
            content_list = result.get("content", [])
            for item in content_list:
                if item.get("type") == "text":
                    return item.get("text", "")
            return ""
        else:
            error_msg = response.error.message if response.error else "Unknown error"
            logger.error(f"Tool '{tool_name}' failed: {error_msg}")
            return f"Lỗi: {error_msg}"
    
    async def close(self) -> None:
        """Close the client and transport."""
        await self.transport.close()
        self._initialized = False
        logger.info("MCP Client closed")
    
    def __repr__(self) -> str:
        return f"<MCPClient: initialized={self._initialized}>"