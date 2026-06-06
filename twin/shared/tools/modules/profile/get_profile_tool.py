"""GetProfileTool - read T3 markdown profile."""
from __future__ import annotations

import logging
from typing import Any, Optional

from twin.shared.memory.profile import SECTION_HEADERS, SECTIONS
from twin.shared.tools.registry.base import BaseTool, ToolExecutionError

logger = logging.getLogger(__name__)


class GetProfileTool(BaseTool):
    """Tool for reading a full T3 profile or one profile section."""

    def __init__(self, profile_store: Optional[Any] = None):
        self.profile_store = profile_store
        logger.debug(
            "GetProfileTool initialized with profile_store=%s",
            profile_store is not None,
        )

    @property
    def name(self) -> str:
        return "get_profile"

    @property
    def description(self) -> str:
        return "Đọc hồ sơ T3."

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "Discord user ID.",
                },
                "section": {
                    "type": "string",
                    "enum": SECTIONS,
                    "description": "Section T3 tùy chọn.",
                },
            },
            "required": ["user_id"],
        }

    async def execute(self, user_id: str, section: Optional[str] = None) -> str:
        user_id = str(user_id or "").strip()
        section = str(section or "").strip() or None

        if not user_id:
            return "Lỗi: Thiếu user_id."
        if not user_id.isdigit():
            logger.warning("T3: invalid user_id for get_profile: %s", user_id)
            return f"Lỗi: user_id '{user_id}' không hợp lệ. Phải là số ID Discord."
        if section is not None and section not in SECTIONS:
            return f"Lỗi: section '{section}' không hợp lệ. Section hợp lệ: {', '.join(SECTIONS)}."
        if not self.profile_store:
            return "Lỗi: MarkdownProfileStore (T3) chưa sẵn sàng."

        try:
            if section is None:
                raw = await self.profile_store.read_raw(user_id)
                return f"Hồ sơ user {user_id}:\n{raw}".rstrip()

            bullets = await self.profile_store.read_section(user_id, section)
            if not bullets:
                return f"Section {section} của user {user_id}: (trống)"
            rendered = "\n".join(f"- {bullet}" for bullet in bullets)
            return f"Section {section} của user {user_id}:\n{rendered}"
        except Exception as e:
            logger.error("T3: get_profile failed: %s", e)
            raise ToolExecutionError(self.name, f"Lỗi hệ thống khi đọc hồ sơ: {e}", original_error=e)

    def __repr__(self) -> str:
        return f"<GetProfileTool: profile_store={self.profile_store is not None}>"
