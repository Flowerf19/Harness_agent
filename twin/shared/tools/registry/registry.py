"""
ToolRegistry - Registry Pattern implementation cho Tool Management.

Registry Pattern:
- Centralized storage for all registered tools
- Dynamic registration (plug-and-play)
- No hardcoded if-else routing
- Easy to add new tools without modifying core code

Design Philosophy:
- Open-Closed Principle (OCP): Open for extension, closed for modification
- Single Responsibility: Each tool manages its own logic
- Dependency Injection: Tools receive dependencies via constructor
"""

import logging
from typing import Dict, List, Optional, Any

from twin.shared.tools.registry.base import BaseTool, ToolExecutionError
from twin.shared.tools.mcp_protocol import ToolDefinition

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Registry for all registered tools.

    Centralized storage that allows:
    - Dynamic tool registration
    - Tool lookup by name
    - Schema retrieval for all tools
    - Tool execution routing

    Attributes:
        _tools: Dict mapping tool name -> BaseTool instance

    Example:
        registry = ToolRegistry()
        registry.register_tool(SearchMemoryTool(episodic_manager))
        registry.register_tool(UpdateProfileTool(core_manager))

        # Get all schemas for LLM
        schemas = registry.get_all_openai_schemas()

        # Execute a tool
        result = await registry.execute_tool("search_memory", {"user_id": "123", "query": "test"})
    """

    def __init__(self, agent_name: str | None = None):
        """Initialize empty registry."""
        self._tools: Dict[str, BaseTool] = {}
        self.agent_name = agent_name
        logger.debug("ToolRegistry initialized agent=%s", agent_name)

    # ==========================================
    # REGISTRATION METHODS
    # ==========================================

    def register_tool(self, tool: BaseTool) -> None:
        """
        Register a tool in the registry.

        Args:
            tool: BaseTool instance to register

        Raises:
            ValueError: If tool with same name already registered
        """
        if tool.name in self._tools:
            logger.warning(f"Tool '{tool.name}' already registered, replacing...")

        self._tools[tool.name] = tool
        logger.debug(f"✅ Registered tool: {tool.name} ({tool.__class__.__name__})")

    def unregister_tool(self, tool_name: str) -> bool:
        """
        Remove a tool from the registry.

        Args:
            tool_name: Name of tool to remove

        Returns:
            bool: True if tool was removed, False if not found
        """
        if tool_name in self._tools:
            del self._tools[tool_name]
            logger.debug(f"🗑️ Unregistered tool: {tool_name}")
            return True
        return False

    def register_tools(self, tools: List[BaseTool]) -> None:
        """
        Register multiple tools at once.

        Args:
            tools: List of BaseTool instances
        """
        for tool in tools:
            self.register_tool(tool)

    # ==========================================
    # LOOKUP METHODS
    # ==========================================

    def get_tool(self, tool_name: str) -> Optional[BaseTool]:
        """
        Get a tool by name.

        Args:
            tool_name: Name of tool to retrieve

        Returns:
            Optional[BaseTool]: Tool instance if found, None otherwise
        """
        return self._tools.get(tool_name)

    def has_tool(self, tool_name: str) -> bool:
        """
        Check if a tool is registered.

        Args:
            tool_name: Name of tool to check

        Returns:
            bool: True if tool exists, False otherwise
        """
        return tool_name in self._tools

    def list_tool_names(self) -> List[str]:
        """
        Get list of all registered tool names.

        Returns:
            List[str]: List of tool names
        """
        return list(self._tools.keys())

    def list_tools(self) -> List[BaseTool]:
        """
        Get list of all registered tool instances.

        Returns:
            List[BaseTool]: List of tool instances
        """
        return list(self._tools.values())

    # ==========================================
    # SCHEMA METHODS
    # ==========================================

    def get_all_openai_schemas(self) -> List[Dict[str, Any]]:
        """
        Get OpenAI-compatible schemas for all registered tools.

        Used by LLM services to provide tool definitions to the model.

        Returns:
            List[Dict[str, Any]]: List of OpenAI tool schemas
        """
        return [
            tool.get_openai_schema()
            for tool in self._tools.values()
            if self._is_visible_to_agent(tool)
        ]

    def get_all_mcp_schemas(self) -> List[ToolDefinition]:
        """
        Get MCP-compatible schemas for all registered tools.

        Used by MCP Server to respond to tools/list requests.

        Returns:
            List[ToolDefinition]: List of MCP tool definitions
        """
        return [
            ToolDefinition.from_base_tool(tool)
            for tool in self._tools.values()
            if self._is_visible_to_agent(tool)
        ]

    def get_tool_schema(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """
        Get OpenAI schema for a specific tool.

        Args:
            tool_name: Name of tool

        Returns:
            Optional[Dict[str, Any]]: Schema if found, None otherwise
        """
        tool = self.get_tool(tool_name)
        if tool and self._is_visible_to_agent(tool):
            return tool.get_openai_schema()
        return None

    # ==========================================
    # EXECUTION METHODS
    # ==========================================

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """
        Execute a tool by name with given arguments.

        This is the main entry point for tool execution.
        Replaces the old if-else routing in ToolManager.

        Args:
            tool_name: Name of tool to execute
            arguments: Dict of arguments matching tool's parameters_schema

        Returns:
            str: Result string from tool execution

        Raises:
            ToolExecutionError: If tool not found or execution fails
        """
        # 1. Lookup tool
        tool = self.get_tool(tool_name)
        if not tool:
            error_msg = f"Tool '{tool_name}' not found in registry"
            logger.error(f"❌ {error_msg}")
            raise ToolExecutionError(tool_name, error_msg)

        allowed_agents = tool.allowed_agents
        if allowed_agents is not None and self.agent_name not in allowed_agents:
            error_msg = (
                f"Agent '{self.agent_name or 'unknown'}' không có quyền dùng tool '{tool_name}'."
            )
            logger.warning("⚠️ %s", error_msg)
            raise ToolExecutionError(tool_name, error_msg)

        # 2. Validate parameters
        validation_error = tool.validate_parameters(arguments)
        if validation_error:
            logger.warning(f"⚠️ Tool '{tool_name}' validation failed: {validation_error}")
            raise ToolExecutionError(tool_name, validation_error)

        # 3. Execute tool
        try:
            result = await tool.execute(**arguments)
            return result
        except Exception as e:
            logger.error(f"❌ Tool '{tool_name}' execution failed: {e}")
            raise ToolExecutionError(tool_name, str(e), original_error=e)

    # ==========================================
    # UTILITY METHODS
    # ==========================================

    def count(self) -> int:
        """
        Get number of registered tools.

        Returns:
            int: Number of tools
        """
        return len(self._tools)

    def _is_visible_to_agent(self, tool: BaseTool) -> bool:
        visible_to_agents = tool.visible_to_agents
        if visible_to_agents is None:
            return True
        return self.agent_name in visible_to_agents

    def clear(self) -> None:
        """
        Remove all registered tools.
        """
        self._tools.clear()
        logger.debug("ToolRegistry cleared")

    def __repr__(self) -> str:
        return f"<ToolRegistry: {self.count()} tools ({', '.join(self.list_tool_names())})>"

    def __len__(self) -> int:
        return self.count()

    def __contains__(self, tool_name: str) -> bool:
        return self.has_tool(tool_name)
