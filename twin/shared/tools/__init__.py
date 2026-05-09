"""
Tools module for Agent capabilities.

Architecture: Hybrid System/MCP
- SystemTool: BaseTool subclasses called directly via ToolRegistry
- MCPProxyTool: BaseTool subclasses that proxy to external MCP servers via MCPClient + HTTPTransport
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
)
from .mcp_client import MCPClient
from .mcp_transport import (
    Transport,
    HTTPTransport,
)
from .tool_discovery import ToolDiscovery, discover_and_register_tools

# Tool implementations
from .implementations.system import (
    SearchMemoryTool,
    UpdateUserProfileTool,
    UpdatePersonalityTool,
)

__all__ = [
    # Core
    "BaseTool",
    "ToolExecutionError",
    "ToolRegistry",
    # MCP Protocol (for external MCP)
    "MCPRequest",
    "MCPResponse",
    "MCPError",
    "ToolDefinition",
    "MCPMethods",
    # MCP Client (for external MCP)
    "MCPClient",
    # Transport
    "Transport",
    "HTTPTransport",
    # Discovery
    "ToolDiscovery",
    "discover_and_register_tools",
    # Implementations
    "SearchMemoryTool",
    "UpdateUserProfileTool",
    "UpdatePersonalityTool",
]