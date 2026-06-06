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
    guide_path: str | None = None
    description_tag: str = "tool_description"


SYSTEM_TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        module="twin.shared.tools.modules.memory.search_memory_tool",
        class_name="SearchMemoryTool",
        guide_path="guides/search_memory.md",
    ),
    ToolSpec(
        module="twin.shared.tools.modules.profile.get_profile_tool",
        class_name="GetProfileTool",
        guide_path="guides/get_profile.md",
    ),
    ToolSpec(
        module="twin.shared.tools.modules.profile.update_profile_tool",
        class_name="UpdateUserProfileTool",
        guide_path="guides/update_user_profile.md",
    ),
    ToolSpec(
        module="twin.shared.tools.modules.profile.update_personality_tool",
        class_name="UpdatePersonalityTool",
        guide_path="guides/update_personality.md",
    ),
    ToolSpec(
        module="twin.shared.tools.modules.web.tavily_search_tool",
        class_name="TavilySearchTool",
        guide_path="guides/web_search.md",
    ),
    ToolSpec(
        module="twin.shared.tools.modules.execution.code_interpreter_tool",
        class_name="CodeInterpreterTool",
        guide_path="guides/run_python_code.md",
    ),
    ToolSpec(
        module="twin.shared.tools.modules.execution.execute_host_bash_tool",
        class_name="ExecuteHostBashTool",
        guide_path="guides/execute_host_bash.md",
    ),
)
