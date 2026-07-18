"""Persona prompt loading, caching, and system-prompt assembly."""
from __future__ import annotations

import logging
from pathlib import Path


class PromptManager:
    """Own static persona Markdown files and assemble the system prompt."""

    _PRIMARY_FILES = ("IDENTITY.md", "SOUL.md")

    def __init__(
        self,
        persona_path: str = "memories",
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self.persona_path = self._resolve_persona_path(persona_path)
        self.logger = logger or logging.getLogger(__name__)
        self.identity = ""
        self.soul = ""
        self.extras: list[str] = []
        self.reload()

    @staticmethod
    def _resolve_persona_path(persona_path: str) -> Path:
        path = Path(persona_path)
        if path.is_absolute():
            return path
        return Path(__file__).resolve().parents[3] / path

    def reload(self) -> None:
        """Reload all persona files after a runtime edit."""
        self.identity = self._load_file("IDENTITY.md")
        self.soul = self._load_file("SOUL.md")
        self.extras = self._load_extras()

    def _load_file(self, filename: str) -> str:
        path = self.persona_path / filename
        try:
            return path.read_text(encoding="utf-8").strip() if path.is_file() else ""
        except OSError as exc:
            self.logger.warning("Unable to load persona prompt %s: %s", path, exc)
            return ""

    def _load_extras(self) -> list[str]:
        if not self.persona_path.is_dir():
            return []
        prompts: list[str] = []
        for path in sorted(self.persona_path.glob("*.md")):
            if path.name in self._PRIMARY_FILES or path.name.startswith("."):
                continue
            content = self._load_file(path.name)
            if content:
                prompts.append(f"## {path.name}\n{content}")
        return prompts

    def build_system_prompt(
        self,
        dynamic_core_prompt: str = "",
        *,
        tool_catalog: str = "",
        include_persona: bool = True,
    ) -> str:
        """Build the final system prompt from static persona and caller context."""
        parts: list[str] = []
        if include_persona:
            identity_parts = [part for part in (self.identity, *self.extras) if part]
            if identity_parts:
                identity_prompt = "\n\n".join(identity_parts)
                parts.append(f"=== NHÂN CÁCH CỦA BẠN ===\n{identity_prompt}")
            if self.soul:
                parts.append(f"=== HƯỚNG DẪN HỘI THOẠI ===\n{self.soul}")
        if tool_catalog:
            parts.append(f"=== CÔNG CỤ ===\n{tool_catalog}")
        if dynamic_core_prompt:
            parts.append(dynamic_core_prompt)
        return "\n\n".join(parts)
