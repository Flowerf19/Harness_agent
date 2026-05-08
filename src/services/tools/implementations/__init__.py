"""
Tool Implementations - Concrete tool classes.

Each file in this directory defines one or more tools that inherit from BaseTool.

Naming Convention:
- File: *_tool.py (e.g., search_memory_tool.py)
- Class: PascalCase (e.g., SearchMemoryTool)

Auto-Discovery:
- ToolDiscovery scans this directory
- Auto-imports and instantiates all tools
- Registers them in ToolRegistry

Available Tools:
- SearchMemoryTool: Query Wiki Pages (T2 consolidated memory)
- UpdateUserProfileTool: Update Core Memory (T3 IDENTITY.md)
- UpdatePersonalityTool: Update bot personality
- TavilySearchTool: Web search via Tavily API
- CodeInterpreterTool: Python code execution in sandbox (CodeBox)
"""

from src.services.tools.implementations.search_memory_tool import SearchMemoryTool
from src.services.tools.implementations.update_profile_tool import UpdateUserProfileTool
from src.services.tools.implementations.update_personality_tool import UpdatePersonalityTool
from src.services.tools.implementations.tavily_search_tool import TavilySearchTool
from src.services.tools.implementations.code_interpreter_tool import CodeInterpreterTool
from src.services.tools.implementations.execute_host_bash_tool import ExecuteHostBashTool

__all__ = [
    "SearchMemoryTool",
    "UpdateUserProfileTool",
    "UpdatePersonalityTool",
    "TavilySearchTool",
    "CodeInterpreterTool",
    "ExecuteHostBashTool",
]