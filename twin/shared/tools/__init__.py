"""
Tools module for Agent capabilities.

Architecture: Local/Remote MCP
- local: BaseTool subclasses called directly via ToolRegistry
- remote_mcp: logical tools that proxy to external MCP servers via MCPClient + HTTPTransport
"""

# Core components
from .registry.base import BaseTool, ToolExecutionError
from .registry.registry import ToolRegistry
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
from .registry.bootstrap import ToolBootstrapResult, build_tool_registry

# Tool implementations
from .modules.memory import SearchMemoryTool
from .modules.profile import (
    GetProfileTool,
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
    "ToolBootstrapResult",
    "build_tool_registry",
    # Implementations
    "SearchMemoryTool",
    "GetProfileTool",
    "UpdateUserProfileTool",
    "UpdatePersonalityTool",
]
