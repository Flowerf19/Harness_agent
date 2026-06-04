"""T3 markdown profile store: per-user `.md` file with 8 fixed sections."""
from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path

from twin.shared.memory.profile.constants import (
    DEFAULT_PROFILE_DIR,
    EMPTY_PLACEHOLDER,
    PROFILE_FOOTER_HINT,
    PROFILE_HEADER,
    SECTION_HEADERS,
    SECTIONS,
)

logger = logging.getLogger(__name__)

_USER_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")
_HEADER_TO_SECTION = {header: key for key, header in SECTION_HEADERS.items()}


def _sanitize_user_id(user_id: str) -> str:
    """Validate user_id is filename-safe; return stripped value or raise."""
    if not isinstance(user_id, str):
        raise ValueError("user_id must be a string")
    cleaned = user_id.strip()
    if not cleaned:
        raise ValueError("user_id must not be empty")
    if not _USER_ID_RE.match(cleaned):
        raise ValueError(
            f"invalid user_id {user_id!r}: only [A-Za-z0-9_-] allowed"
        )
    return cleaned


def _empty_section_map() -> dict[str, list[str]]:
    """Fresh map: section_key -> [] (empty list = render placeholder)."""
    return {key: [] for key in SECTIONS}


def _parse_markdown(text: str) -> dict[str, list[str]]:
    """Parse markdown into {section_key: [bullet, ...]} (placeholder dropped)."""
    sections = _empty_section_map()
    current: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line.startswith("## "):
            header = line[3:].strip()
            current = _HEADER_TO_SECTION.get(header)
            continue
        if current is None:
            continue
        if not line.startswith("- "):
            continue
        bullet = line[2:].strip()
        if not bullet:
            continue
        if bullet == EMPTY_PLACEHOLDER:
            continue
        sections[current].append(bullet)
    return sections


def _render_markdown(sections: dict[str, list[str]]) -> str:
    """Render canonical markdown: 8 headers in SECTIONS order, placeholders for empties."""
    parts: list[str] = []
    for idx, key in enumerate(SECTIONS):
        parts.append(f"## {SECTION_HEADERS[key]}")
        bullets = sections.get(key) or []
        if bullets:
            for b in bullets:
                parts.append(f"- {b}")
        else:
            parts.append(f"- {EMPTY_PLACEHOLDER}")
        if idx != len(SECTIONS) - 1:
            parts.append("")
    return "\n".join(parts) + "\n"


def _default_skeleton() -> str:
    return _render_markdown(_empty_section_map())


class MarkdownProfileStore:
    """Per-user markdown profile store (T3).

    File: ``<base_path>/<user_id>.md`` with 8 fixed sections.
    Reads are unlocked; writes for the same user are serialized via
    a per-user ``asyncio.Lock``.
    """

    def __init__(self, base_path: str = DEFAULT_PROFILE_DIR) -> None:
        self._base_path = Path(base_path)
        self._base_path.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, asyncio.Lock] = {}

    # ------------------------------------------------------------------ helpers

    def _path_for(self, user_id: str) -> Path:
        cleaned = _sanitize_user_id(user_id)
        return self._base_path / f"{cleaned}.md"

    def _lock_for(self, user_id: str) -> asyncio.Lock:
        cleaned = _sanitize_user_id(user_id)
        lock = self._locks.get(cleaned)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[cleaned] = lock
        return lock

    @staticmethod
    def _read_text_sync(path: Path) -> str | None:
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()

    @staticmethod
    def _atomic_write_sync(path: Path, content: str) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp, path)

    async def _ensure_file(self, path: Path) -> str:
        """Return current file text; create default skeleton if missing."""
        text = self._read_text_sync(path)
        if text is not None:
            return text
        skeleton = _default_skeleton()
        try:
            self._atomic_write_sync(path, skeleton)
        except OSError as exc:
            logger.warning("profile skeleton write failed for %s: %s", path, exc)
            raise
        return skeleton

    # ----------------------------------------------------------------- reads

    async def read_raw(self, user_id: str) -> str:
        """Return full markdown text. Auto-creates default skeleton on first read."""
        path = self._path_for(user_id)
        return await self._ensure_file(path)

    async def read_section(self, user_id: str, section: str) -> list[str]:
        """Return bullets for a section, excluding the empty-placeholder."""
        if section not in SECTIONS:
            raise ValueError(f"invalid section: {section!r}")
        text = await self.read_raw(user_id)
        parsed = _parse_markdown(text)
        return list(parsed.get(section, []))

    async def read_section_if_exists(self, user_id: str, section: str) -> list[str]:
        """Return section bullets only when the profile file already exists."""
        if section not in SECTIONS:
            raise ValueError(f"invalid section: {section!r}")
        path = self._path_for(user_id)
        text = self._read_text_sync(path)
        if text is None:
            return []
        parsed = _parse_markdown(text)
        return list(parsed.get(section, []))

    async def get_system_prompt_context(self, user_id: str) -> str:
        """Render profile as a system-prompt block; '' if every section empty."""
        text = await self.read_raw(user_id)
        parsed = _parse_markdown(text)
        non_empty = [(k, parsed[k]) for k in SECTIONS if parsed.get(k)]
        if not non_empty:
            return ""
        lines: list[str] = [PROFILE_HEADER]
        for idx, (key, bullets) in enumerate(non_empty):
            lines.append(f"## {SECTION_HEADERS[key]}")
            for b in bullets:
                lines.append(f"- {b}")
            if idx != len(non_empty) - 1:
                lines.append("")
        lines.append("")
        lines.append(PROFILE_FOOTER_HINT)
        return "\n".join(lines)

    # ---------------------------------------------------------------- writes

    async def append_raw(
        self,
        user_id: str,
        section: str,
        content: str,
        source_memory_id: str | None = None,  # accepted for API stability
    ) -> bool:
        """Append a bullet. Returns True on append, False on skip.

        Skips silently when content is empty or duplicates an existing bullet
        (case-insensitive, post-strip). Replaces the placeholder when the
        section is currently empty.
        """
        del source_memory_id  # not stored; reserved for future provenance
        if section not in SECTIONS:
            raise ValueError(f"invalid section: {section!r}")
        path = self._path_for(user_id)
        bullet = (content or "").strip()
        if not bullet:
            return False

        lock = self._lock_for(user_id)
        async with lock:
            text = await self._ensure_file(path)
            parsed = _parse_markdown(text)
            existing = parsed.get(section, [])
            lowered = {b.strip().lower() for b in existing}
            if bullet.lower() in lowered:
                return False
            existing.append(bullet)
            parsed[section] = existing
            new_text = _render_markdown(parsed)
            try:
                self._atomic_write_sync(path, new_text)
            except OSError as exc:
                logger.warning("profile append failed for %s: %s", path, exc)
                raise
            logger.debug(
                "profile append: user=%s section=%s len=%d",
                user_id, section, len(bullet),
            )
            return True

    async def write_raw(self, user_id: str, new_content: str) -> bool:
        """Overwrite full file atomically. Caller owns diff/validation gate."""
        path = self._path_for(user_id)
        lock = self._lock_for(user_id)
        async with lock:
            try:
                self._atomic_write_sync(path, new_content)
            except OSError as exc:
                logger.warning("profile write failed for %s: %s", path, exc)
                raise
            logger.debug(
                "profile write: user=%s bytes=%d", user_id, len(new_content)
            )
            return True

