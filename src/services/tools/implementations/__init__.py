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
- SearchMemoryTool: Query Episodic Memory (T2)
- UpdateUserProfileTool: Update Core Memory (T3)
- UpdatePersonalityTool: Update IDENTITY.md
- TavilySearchTool: Web search via Tavily API
"""

from src.services.tools.implementations.search_memory_tool import SearchMemoryTool
from src.services.tools.implementations.update_profile_tool import UpdateUserProfileTool
from src.services.tools.implementations.update_personality_tool import UpdatePersonalityTool
from src.services.tools.implementations.tavily_search_tool import TavilySearchTool

__all__ = [
    "SearchMemoryTool",
    "UpdateUserProfileTool",
    "UpdatePersonalityTool",
    "TavilySearchTool",
]