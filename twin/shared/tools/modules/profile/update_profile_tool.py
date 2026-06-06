"""UpdateUserProfileTool - append bullets to T3 markdown profile."""
from __future__ import annotations

import logging
from typing import Any, Optional

from twin.shared.memory.profile import SECTION_HEADERS, SECTIONS
from twin.shared.tools.registry.base import BaseTool, ToolExecutionError

logger = logging.getLogger(__name__)


class UpdateUserProfileTool(BaseTool):
    """Tool for appending one bullet to a user's T3 profile section."""

    def __init__(
        self,
        profile_store: Optional[Any] = None,
        core_manager: Optional[Any] = None,
    ):
        self.profile_store = profile_store
        if self.profile_store is None and hasattr(core_manager, "append_raw"):
            self.profile_store = core_manager
        logger.debug(
            "UpdateUserProfileTool initialized with profile_store=%s",
            self.profile_store is not None,
        )

    @property
    def name(self) -> str:
        return "update_user_profile"

    @property
    def description(self) -> str:
        return "Lưu một thông tin T3."

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
                    "description": "Section T3.",
                },
                "content": {
                    "type": "string",
                    "description": "Bullet không có prefix '- '.",
                },
                "source_memory_id": {
                    "type": "string",
                    "description": "T2 source id tùy chọn.",
                },
            },
            "required": ["user_id", "section", "content"],
        }

    async def execute(
        self,
        user_id: str,
        section: str,
        content: str,
        source_memory_id: Optional[str] = None,
    ) -> str:
        user_id = str(user_id or "").strip()
        section = str(section or "").strip()
        content = str(content or "").strip()

        if not user_id or not content:
            return "Lỗi: Thiếu user_id hoặc nội dung hồ sơ."

        if not user_id.isdigit():
            logger.warning("T3: invalid user_id for update_user_profile: %s", user_id)
            return f"Lỗi: user_id '{user_id}' không hợp lệ. Phải là số ID Discord."

        if section not in SECTIONS:
            return f"Lỗi: section '{section}' không hợp lệ. Section hợp lệ: {', '.join(SECTIONS)}."

        if not self.profile_store:
            return "Lỗi: MarkdownProfileStore (T3) chưa sẵn sàng."

        try:
            appended = await self.profile_store.append_raw(
                user_id,
                section,
                content,
                source_memory_id=source_memory_id,
            )
            if not appended:
                return f"Không thay đổi: nội dung trống hoặc đã tồn tại trong section {section}."
            logger.info("T3: appended profile bullet user=%s section=%s", user_id, section)
            return f"Đã cập nhật hồ sơ user {user_id}, section {section}."
        except Exception as e:
            logger.error("T3: update_user_profile failed: %s", e)
            raise ToolExecutionError(self.name, f"Lỗi hệ thống khi lưu hồ sơ: {e}", original_error=e)

    def __repr__(self) -> str:
        return f"<UpdateUserProfileTool: profile_store={self.profile_store is not None}>"
