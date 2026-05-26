"""
BaseTool - Abstract base class cho tất cả Tools trong hệ thống MCP.

Mỗi Tool phải kế thừa từ BaseTool và implement:
- name: Tên định danh của tool
- description: Mô tả chức năng cho LLM hiểu
- parameters_schema: JSON Schema của parameters
- execute(): Logic thực thi tool

Design Pattern: Template Method + Strategy
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Set


class BaseTool(ABC):
    """
    Abstract base class cho tất cả Tools.

    Mỗi tool là một thực thể độc lập, tự quản lý:
    - Schema definition (OpenAI/MCP format)
    - Execution logic
    - Error handling

    Attributes:
        name: Tên định danh (VD: "search_memory")
        description: Mô tả cho LLM (VD: "Tìm kiếm ký ức...")
        parameters_schema: JSON Schema dict
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Tên định danh của tool.
        Must be unique across all registered tools.

        Returns:
            str: Tool name (VD: "search_memory")
        """
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """
        Mô tả chức năng của tool cho LLM.
        LLM sẽ đọc description để quyết định khi nào dùng tool.

        Returns:
            str: Human-readable description
        """
        pass

    @property
    @abstractmethod
    def parameters_schema(self) -> Dict[str, Any]:
        """
        JSON Schema của parameters.
        Theo chuẩn OpenAI Function Calling.

        Format:
        {
            "type": "object",
            "properties": {
                "param_name": {
                    "type": "string",
                    "description": "Mô tả parameter"
                }
            },
            "required": ["param_name"]
        }

        Returns:
            Dict[str, Any]: JSON Schema dict
        """
        pass

    @property
    def allowed_agents(self) -> Optional[Set[str]]:
        """
        Agents allowed to execute this tool.

        None means every agent can execute it.
        """
        return None

    @property
    def visible_to_agents(self) -> Optional[Set[str]]:
        """
        Agents allowed to see this tool in LLM schemas.

        None means every agent can see it.
        """
        return None

    @abstractmethod
    async def execute(self, **kwargs) -> str:
        """
        Thực thi tool với các parameters được truyền.

        Args:
            **kwargs: Parameters matching parameters_schema

        Returns:
            str: Result string để LLM đọc và hiểu
            (Should be human-readable, not JSON)

        Raises:
            ToolExecutionError: Nếu tool execution fails
        """
        pass

    # ==========================================
    # HELPER METHODS - Tự generate schemas
    # ==========================================

    def get_openai_schema(self) -> Dict[str, Any]:
        """
        Generate OpenAI-compatible tool schema.

        Format:
        {
            "type": "function",
            "function": {
                "name": "...",
                "description": "...",
                "parameters": {...}
            }
        }

        Returns:
            Dict[str, Any]: OpenAI tool definition
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema
            }
        }

    def get_mcp_schema(self) -> Dict[str, Any]:
        """
        Generate MCP-compatible tool schema.

        MCP format (Anthropic's Model Context Protocol):
        {
            "name": "...",
            "description": "...",
            "inputSchema": {...}
        }

        Note: MCP uses "inputSchema" instead of "parameters"

        Returns:
            Dict[str, Any]: MCP tool definition
        """
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.parameters_schema
        }

    def validate_parameters(self, params: Dict[str, Any]) -> Optional[str]:
        """
        Validate parameters against schema.

        Args:
            params: Parameters dict to validate

        Returns:
            Optional[str]: Error message if validation fails, None if valid
        """
        required = self.parameters_schema.get("required", [])

        # Check required parameters
        for param_name in required:
            if param_name not in params:
                return f"Missing required parameter: '{param_name}'"
            if params[param_name] is None or params[param_name] == "":
                return f"Parameter '{param_name}' cannot be empty"

        return None

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: {self.name}>"


class ToolExecutionError(Exception):
    """
    Exception raised khi tool execution fails.

    Attributes:
        tool_name: Name of the tool that failed
        message: Error message
        original_error: Original exception (if any)
    """

    def __init__(self, tool_name: str, message: str, original_error: Optional[Exception] = None):
        self.tool_name = tool_name
        self.message = message
        self.original_error = original_error
        super().__init__(f"Tool '{tool_name}' failed: {message}")

    def __repr__(self) -> str:
        return f"ToolExecutionError(tool={self.tool_name}, message={self.message})"
