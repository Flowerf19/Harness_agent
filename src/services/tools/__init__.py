"""
Tools module for Agent capabilities.

Architecture: MCP Client-Server with Registry Pattern
- BaseTool: Abstract base class for all tools
- ToolRegistry: Centralized tool storage and execution
- MCPServer: JSON-RPC 2.0 server for tool management
- MCPClient: Client for communicating with MCP server
- ToolDiscovery: Auto-discovery system for tools
- Transport: Communication layer (inmemory, stdio, http)
"""

# Core components
from .base_tool import BaseTool, ToolExecutionError
from .tool_registry import ToolRegistry
from .mcp_protocol import (
    MCPRequest,
    MCPResponse,
    MCPError,
    ToolDefinition,
    MCPMethods,
    MCPServerInfo,
    MCPCapabilities,
)
from .mcp_server import MCPServer
from .mcp_client import MCPClient, ToolCallResult
from .mcp_transport import (
    Transport,
    InMemoryTransport,
    StdioTransport,
    HTTPTransport,
    create_transport,
)
from .tool_discovery import ToolDiscovery, discover_and_register_tools

# Tool implementations
from .implementations import (
    SearchMemoryTool,
    UpdateUserProfileTool,
    UpdatePersonalityTool,
)

__all__ = [
    # Core
    "BaseTool",
    "ToolExecutionError",
    "ToolRegistry",
    # MCP Protocol
    "MCPRequest",
    "MCPResponse",
    "MCPError",
    "ToolDefinition",
    "MCPMethods",
    "MCPServerInfo",
    "MCPCapabilities",
    # MCP Server/Client
    "MCPServer",
    "MCPClient",
    "ToolCallResult",
    # Transport
    "Transport",
    "InMemoryTransport",
    "StdioTransport",
    "HTTPTransport",
    "create_transport",
    # Discovery
    "ToolDiscovery",
    "discover_and_register_tools",
    # Implementations
    "SearchMemoryTool",
    "UpdateUserProfileTool",
    "UpdatePersonalityTool",
]