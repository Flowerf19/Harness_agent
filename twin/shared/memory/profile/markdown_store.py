"""T3 markdown profile store: per-user `.md` file with 8 fixed sections."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import fcntl
import hashlib
import logging
import os
import re
from pathlib import Path
from typing import Any

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


def profile_hash(text: str) -> str:
    """SHA256 of the raw profile markdown."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _default_skeleton() -> str:
    return _render_markdown(_empty_section_map())


def _sanitize_bullets(bullets: list[str]) -> list[str]:
    if not isinstance(bullets, list):
        raise ValueError("bullets must be a list")

    cleaned: list[str] = []
    for idx, bullet in enumerate(bullets):
        if not isinstance(bullet, str):
            raise ValueError(f"bullet #{idx + 1} must be a string")
        value = bullet.strip()
        if not value:
            raise ValueError(f"bullet #{idx + 1} must not be empty")
        if "\n" in value or "\r" in value:
            raise ValueError(f"bullet #{idx + 1} must be a single line")
        if value.startswith("- "):
            raise ValueError(f"bullet #{idx + 1} must not include '- ' prefix")
        cleaned.append(value)
    return cleaned


class MarkdownProfileStore:
    """Per-user markdown profile store (T3).

    File: ``<base_path>/<user_id>.md`` with 8 fixed sections.
    Per-user read/create and write operations are serialized both within the
    current event loop and across processes sharing the same profile directory.
    """

    def __init__(
        self,
        base_path: str = DEFAULT_PROFILE_DIR,
        *,
        enable_file_lock: bool = True,
        file_lock_poll_seconds: float = 0.05,
    ) -> None:
        self._base_path = Path(base_path)
        self._base_path.mkdir(parents=True, exist_ok=True)
        self._lock_path = self._base_path / ".locks"
        self._lock_path.mkdir(parents=True, exist_ok=True)
        self._enable_file_lock = enable_file_lock
        self._file_lock_poll_seconds = file_lock_poll_seconds
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

    def _file_lock_path_for(self, user_id: str) -> Path:
        cleaned = _sanitize_user_id(user_id)
        return self._lock_path / f"{cleaned}.lock"

    @asynccontextmanager
    async def _profile_file_lock(self, user_id: str):
        """Per-user lock shared by March7/Evernight processes."""
        async_lock = self._lock_for(user_id)
        async with async_lock:
            if not self._enable_file_lock:
                yield
                return

            lock_path = self._file_lock_path_for(user_id)
            with open(lock_path, "a", encoding="utf-8") as lock_file:
                while True:
                    try:
                        fcntl.flock(
                            lock_file.fileno(),
                            fcntl.LOCK_EX | fcntl.LOCK_NB,
                        )
                        break
                    except BlockingIOError:
                        await asyncio.sleep(self._file_lock_poll_seconds)
                try:
                    yield
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

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
        async with self._profile_file_lock(user_id):
            return await self._ensure_file(path)

    async def read_raw_hash(self, user_id: str) -> str:
        """Return SHA256 hash of the current raw markdown profile."""
        return profile_hash(await self.read_raw(user_id))

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

        async with self._profile_file_lock(user_id):
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
        async with self._profile_file_lock(user_id):
            try:
                self._atomic_write_sync(path, new_content)
            except OSError as exc:
                logger.warning("profile write failed for %s: %s", path, exc)
                raise
            logger.debug(
                "profile write: user=%s bytes=%d", user_id, len(new_content)
            )
            return True

    async def replace_section(
        self,
        user_id: str,
        section: str,
        bullets: list[str],
        expected_profile_hash: str | None = None,
    ) -> dict[str, Any]:
        """Replace exactly one canonical section with clean bullets.

        ``expected_profile_hash`` is the SHA256 of the raw current profile.
        When provided and stale, no write occurs and the result reports a
        conflict with the current hash.
        """
        if section not in SECTIONS:
            raise ValueError(f"invalid section: {section!r}")
        cleaned_bullets = _sanitize_bullets(bullets)
        expected = (expected_profile_hash or "").strip() or None
        path = self._path_for(user_id)

        async with self._profile_file_lock(user_id):
            text = await self._ensure_file(path)
            current_hash = profile_hash(text)
            if expected is not None and expected != current_hash:
                return {
                    "ok": False,
                    "conflict": True,
                    "section": section,
                    "profile_hash": current_hash,
                    "expected_profile_hash": expected,
                    "written": False,
                }

            parsed = _parse_markdown(text)
            before = list(parsed.get(section, []))
            parsed[section] = cleaned_bullets
            new_text = _render_markdown(parsed)
            new_hash = profile_hash(new_text)
            if new_text != text:
                try:
                    self._atomic_write_sync(path, new_text)
                except OSError as exc:
                    logger.warning("profile section replace failed for %s: %s", path, exc)
                    raise

            logger.debug(
                "profile section replace: user=%s section=%s before=%d after=%d",
                user_id, section, len(before), len(cleaned_bullets),
            )
            return {
                "ok": True,
                "conflict": False,
                "section": section,
                "profile_hash": new_hash,
                "previous_profile_hash": current_hash,
                "written": new_text != text,
                "old_count": len(before),
                "new_count": len(cleaned_bullets),
            }
