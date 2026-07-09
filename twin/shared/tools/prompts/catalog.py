"""Micro-catalog and lazy guide rendering for native tools."""
from __future__ import annotations

import re

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from twin.shared.tools.declarations.system_tools import ToolSpec
from twin.shared.tools.registry.base import BaseTool


_PROMPTS_DIR = Path(__file__).parent
DEFAULT_DESCRIPTION_TAG = "tool_description"


@dataclass(frozen=True, slots=True)
class ToolPromptSpec:
    name: str
    guide_path: Path
    description_tag: str = DEFAULT_DESCRIPTION_TAG


class ToolPromptCatalog:
    """Render short tool catalog at startup and full guide after selection."""

    def __init__(self, specs: Iterable[ToolPromptSpec]):
        self._specs: dict[str, ToolPromptSpec] = {}
        for spec in specs:
            if not spec.name:
                raise ValueError("Tool prompt spec name cannot be empty")
            self._specs[spec.name] = spec

    @classmethod
    def from_tools_and_specs(
        cls,
        tools: Iterable[BaseTool],
        specs: Iterable[ToolSpec],
        *,
        agent_name: str | None = None,
    ) -> "ToolPromptCatalog":
        by_class = {spec.class_name: spec for spec in specs}
        prompt_specs: list[ToolPromptSpec] = []
        for tool in tools:
            if not _is_visible_to_agent(tool, agent_name):
                continue

            spec = _find_spec_for_tool(tool, by_class)
            if spec is None:
                raise ValueError(f"Missing tool declaration for visible tool: {tool.name}")
            if not spec.guide_path:
                raise ValueError(f"Missing guide_path for visible tool: {tool.name}")

            guide_path = Path(spec.guide_path)
            if not guide_path.is_absolute():
                guide_path = _PROMPTS_DIR / guide_path

            prompt_specs.append(
                ToolPromptSpec(
                    name=tool.name,
                    guide_path=guide_path,
                    description_tag=spec.description_tag,
                )
            )

        return cls(prompt_specs)

    def render_catalog(self) -> str:
        if not self._specs:
            return ""

        lines = []
        for name in sorted(self._specs):
            lines.append(f"- {name}: {self.render_tool_description(name)}")
        return "\n\n".join(lines)

    def render_tool_guide(self, tool_name: str) -> str:
        body = self._guide_body(tool_name)
        return f'<tool_guide name="{tool_name}">\n{body}\n</tool_guide>'

    def render_tool_description(self, tool_name: str) -> str:
        spec = self._get(tool_name)
        return read_tool_description(spec.name, spec.guide_path, spec.description_tag)

    def has_guide(self, tool_name: str) -> bool:
        return tool_name in self._specs

    def allowed_tool_names(self) -> set[str]:
        return set(self._specs)

    def _guide_body(self, tool_name: str) -> str:
        spec = self._get(tool_name)
        body = _read_guide(spec)
        start_tag = f"<{spec.description_tag}>"
        end_tag = f"</{spec.description_tag}>"
        return body.replace(start_tag, "").replace(end_tag, "").strip()

    def _get(self, tool_name: str) -> ToolPromptSpec:
        try:
            return self._specs[tool_name]
        except KeyError as exc:
            raise KeyError(f"Unknown tool guide: {tool_name}") from exc


_INCLUDE_RE = re.compile(r"(?m)^[ \t]*@include[ \t]+(\S+)[ \t]*$")


def _resolve_includes(body: str, base_dir: Path) -> str:
    """Inline `@include <relpath>` lines with the referenced guide file.

    Paths resolve against the directory of the including guide (``base_dir``),
    so a guide includes a sibling by name (`@include sibling.md`). Absolute
    paths are used as-is. Single level only (included files are not re-scanned).
    Missing targets raise so a broken include fails loudly instead of silently
    dropping content.
    """

    def _repl(match: re.Match[str]) -> str:
        rel = match.group(1)
        target = Path(rel)
        if not target.is_absolute():
            target = base_dir / target
        if not target.exists():
            raise FileNotFoundError(f"@include target not found: {target}")
        return target.read_text(encoding="utf-8")

    return _INCLUDE_RE.sub(_repl, body)


def _read_guide(spec: ToolPromptSpec) -> str:
    if not spec.guide_path.exists():
        raise FileNotFoundError(f"Tool guide not found for {spec.name}: {spec.guide_path}")
    body = spec.guide_path.read_text(encoding="utf-8")
    body = _resolve_includes(body, base_dir=spec.guide_path.parent)
    return body.strip()


def read_tool_description(
    tool_name: str,
    guide_path: str | Path,
    description_tag: str = DEFAULT_DESCRIPTION_TAG,
) -> str:
    guide = Path(guide_path)
    if not guide.is_absolute():
        guide = _PROMPTS_DIR / guide
    spec = ToolPromptSpec(
        name=tool_name,
        guide_path=guide,
        description_tag=description_tag,
    )
    body = _read_guide(spec)
    start_tag = f"<{description_tag}>"
    end_tag = f"</{description_tag}>"
    start = body.find(start_tag)
    end = body.find(end_tag)
    if start == -1 or end == -1 or end <= start:
        raise ValueError(
            f"Tool guide missing <{description_tag}> block for {tool_name}: {guide}"
        )
    description = body[start + len(start_tag):end].strip()
    return description


def _find_spec_for_tool(
    tool: BaseTool,
    specs_by_class: dict[str, ToolSpec],
) -> ToolSpec | None:
    inner_tool = getattr(tool, "_tool", tool)
    return specs_by_class.get(inner_tool.__class__.__name__)


def _is_visible_to_agent(tool: BaseTool, agent_name: str | None) -> bool:
    visible_to = tool.visible_to_agents
    return visible_to is None or agent_name in visible_to
