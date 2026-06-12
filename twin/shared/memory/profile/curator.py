"""T3 auto-curation: 1 LLM call to dedup/merge/drop stale profile bullets.

The curator reads the full T3 profile, asks the LLM for a deduped canonical
section map, and writes it back via ``replace_all`` under the same optimistic-
concurrency guard the manual tool uses. ``curate`` never raises — every failure
mode (LLM error, parse error, conflict, shrink-blocked) maps to a status dict so
the fire-and-forget scheduler can never reach the chat path.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from twin.shared.memory.profile.constants import (
    DEFAULT_PROFILE_DIR,
    PROFILE_CURATION_MAX_TOKENS,
    PROFILE_CURATION_MIN_BULLETS,
    SECTIONS,
)
from twin.shared.memory.profile.markdown_store import (
    _parse_markdown,
    _render_markdown,
    _sanitize_user_id,
    profile_hash,
)
from twin.shared.memory.timeline.extractor import STRICT_JSON_SUFFIX, _extract_json

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "Bạn là bộ biên tập hồ sơ người dùng. Đầu vào là hồ sơ T3 với 8 section cố "
    "định. Nhiệm vụ: gộp các bullet trùng/diễn đạt lại, bỏ thông tin lỗi thời/đã "
    "bị mâu thuẫn, GIỮ nguyên 8 section (không tạo section mới), không bịa thông "
    "tin mới. Trả về DUY NHẤT JSON: "
    '{"sections": {"basic":[...], "contact":[...], "relationship":[...], '
    '"work":[...], "interest":[...], "habit":[...], "psychological":[...], '
    '"rules":[...]}}. Mỗi bullet là một dòng ngắn, không prefix "- ". Section '
    "không có gì thì trả mảng rỗng."
)


class ProfileCurator:
    """1 LLM call: dedup/merge/drop the full T3 profile, then rewrite it."""

    def __init__(self, profile_store, llm) -> None:
        self.profile_store = profile_store
        self.llm = llm
        self.logger = logging.getLogger(__name__)

    # -------------------------------------------------------------- marker

    def _curation_dir(self) -> Path:
        base = getattr(self.profile_store, "_base_path", None)
        base_path = Path(base) if base is not None else Path(DEFAULT_PROFILE_DIR)
        return base_path / ".curation"

    def _marker_path(self, user_id: str) -> Path:
        cleaned = _sanitize_user_id(user_id)
        return self._curation_dir() / f"{cleaned}.hash"

    def _last_curated_hash(self, user_id: str) -> str:
        try:
            return self._marker_path(user_id).read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return ""
        except OSError as exc:
            self.logger.warning("T3:curator: marker read failed: %s", exc)
            return ""

    def _set_last_curated_hash(self, user_id: str, hash_value: str) -> None:
        path = self._marker_path(user_id)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(hash_value, encoding="utf-8")
        except OSError as exc:
            self.logger.warning("T3:curator: marker write failed: %s", exc)

    # -------------------------------------------------------------- curate

    async def curate(self, user_id: str) -> dict:
        """Dedup/clean the user's T3 profile. Never raises; returns a status dict.

        Statuses: ``ok`` / ``skip_trivial`` / ``skip_unchanged`` /
        ``parse_failed`` / ``conflict`` / ``shrink_blocked`` / ``write_rejected``
        / ``error``.
        """
        try:
            text = await self.profile_store.read_raw(user_id)
            current_hash = profile_hash(text)
            parsed = _parse_markdown(text)
            total = sum(len(parsed.get(s, [])) for s in SECTIONS)
            if total < PROFILE_CURATION_MIN_BULLETS:
                return {"status": "skip_trivial"}
            if self._last_curated_hash(user_id) == current_hash:
                return {"status": "skip_unchanged"}

            sections = await self._curate_llm(parsed)
            if sections is None:
                return {"status": "parse_failed"}

            result = await self.profile_store.replace_all(
                user_id, sections, expected_profile_hash=current_hash,
            )
            if result.get("conflict"):
                return {"status": "conflict"}
            if result.get("shrink_blocked"):
                return {"status": "shrink_blocked"}
            if not result.get("ok"):
                # Parsing succeeded; the store refused the write for some other
                # reason. Report it honestly rather than as a parse failure.
                return {"status": "write_rejected"}

            new_hash = result.get("profile_hash", current_hash)
            self._set_last_curated_hash(user_id, new_hash)
            return {
                "status": "ok",
                "profile_hash": new_hash,
                "old_total": result.get("old_total"),
                "new_total": result.get("new_total"),
            }
        except Exception as exc:  # never reach the chat path
            self.logger.warning(
                "T3:curator: curate failed for %s: %s", user_id, exc, exc_info=True,
            )
            return {"status": "error"}

    async def _curate_llm(self, parsed: dict[str, list[str]]) -> dict[str, list[str]] | None:
        """One LLM call (one strict retry) → validated section map, or None on failure."""
        snapshot = _render_markdown(parsed)
        attempts = (SYSTEM_PROMPT, SYSTEM_PROMPT + STRICT_JSON_SUFFIX)
        for attempt, system_prompt in enumerate(attempts):
            try:
                response = await self.llm.generate_response(
                    messages=[{"role": "user", "content": snapshot}],
                    system_prompt=system_prompt,
                    use_native_tools=False,
                    max_tokens=PROFILE_CURATION_MAX_TOKENS,
                )
            except Exception as exc:
                self.logger.warning("T3:curator: LLM call failed: %s", exc, exc_info=True)
                return None

            text = getattr(response, "content", None)
            if not isinstance(text, str):
                text = str(response) if response is not None else ""

            try:
                data = json.loads(_extract_json(text))
                return _validate_sections(data)
            except Exception as exc:
                if attempt + 1 < len(attempts):
                    self.logger.info(
                        "T3:curator: parse failed (attempt %d), retrying strict: %s",
                        attempt + 1, exc,
                    )
                    continue
                self.logger.warning(
                    "T3:curator: JSON parse/validate failed: %s | raw=%r",
                    exc, text[:300],
                )
                return None
        return None


def _validate_sections(data) -> dict[str, list[str]]:
    """Coerce parsed JSON into {canonical_section: [str, ...]}; drop unknown keys."""
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    raw_sections = data.get("sections")
    if not isinstance(raw_sections, dict):
        raise ValueError("missing 'sections' object")
    cleaned: dict[str, list[str]] = {}
    for key in SECTIONS:
        bullets = raw_sections.get(key)
        if not isinstance(bullets, list):
            cleaned[key] = []
            continue
        cleaned[key] = [str(b).strip() for b in bullets if str(b).strip()]
    return cleaned
