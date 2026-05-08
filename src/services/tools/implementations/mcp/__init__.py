"""
MCP Proxy Tools - BaseTool subclasses that proxy to external MCP servers.

These tools use MCPClient + HTTPTransport to call tools on remote MCP servers.
They inherit from BaseTool so ToolRegistry and ChatCoordinator don't need
to know they're proxies - they look like any other tool to the system.
"""

__all__ = []
