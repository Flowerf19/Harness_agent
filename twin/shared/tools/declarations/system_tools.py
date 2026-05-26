"""System tool catalog.

This file is the audit point for in-process tools: what exists, where its
implementation lives, and which agents may see or execute it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ToolSpec:
    module: str
    class_name: str
    visible_to: Optional[frozenset[str]] = None
    allowed_to: Optional[frozenset[str]] = None


SYSTEM_TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        module="twin.shared.tools.modules.memory.search_memory_tool",
        class_name="SearchMemoryTool",
    ),
    ToolSpec(
        module="twin.shared.tools.modules.memory.consolidate_t2_memory_tool",
        class_name="ConsolidateT2MemoryTool",
        visible_to=frozenset({"evernight"}),
        allowed_to=frozenset({"evernight"}),
    ),
    ToolSpec(
        module="twin.shared.tools.modules.profile.update_profile_tool",
        class_name="UpdateUserProfileTool",
    ),
    ToolSpec(
        module="twin.shared.tools.modules.profile.update_personality_tool",
        class_name="UpdatePersonalityTool",
    ),
    ToolSpec(
        module="twin.shared.tools.modules.web.tavily_search_tool",
        class_name="TavilySearchTool",
    ),
    ToolSpec(
        module="twin.shared.tools.modules.execution.code_interpreter_tool",
        class_name="CodeInterpreterTool",
    ),
    ToolSpec(
        module="twin.shared.tools.modules.execution.execute_host_bash_tool",
        class_name="ExecuteHostBashTool",
    ),
)
