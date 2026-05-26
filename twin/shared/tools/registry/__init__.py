"""Tool framework primitives and bootstrap helpers."""

from twin.shared.tools.registry.base import BaseTool, ToolExecutionError
from twin.shared.tools.registry.registry import ToolRegistry
from twin.shared.tools.registry.discovery import ToolDiscovery, discover_and_register_tools
from twin.shared.tools.registry.bootstrap import ToolBootstrapResult, build_tool_registry

__all__ = [
    "BaseTool",
    "ToolExecutionError",
    "ToolRegistry",
    "ToolDiscovery",
    "discover_and_register_tools",
    "ToolBootstrapResult",
    "build_tool_registry",
]
