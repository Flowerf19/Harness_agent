"""ManageUserProfileTool - curate T3 markdown profile sections."""
from __future__ import annotations

import logging
from typing import Any, Optional

from twin.shared.memory.profile import SECTIONS
from twin.shared.tools.registry.base import BaseTool, ToolExecutionError

logger = logging.getLogger(__name__)


class ManageUserProfileTool(BaseTool):
    """Tool for destructive/curation edits to one T3 profile section."""

    def __init__(self, profile_store: Optional[Any] = None):
        self.profile_store = profile_store
        logger.debug(
            "ManageUserProfileTool initialized with profile_store=%s",
            profile_store is not None,
        )

    @property
    def name(self) -> str:
        return "manage_user_profile"

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "Discord user ID dạng số.",
                },
                "section": {
                    "type": "string",
                    "enum": SECTIONS,
                    "description": "Một section T3 cần curate.",
                },
                "bullets": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Danh sách bullet sạch, không prefix '- '.",
                },
                "expected_profile_hash": {
                    "type": "string",
                    "description": "SHA256 của raw profile hiện tại từ get_profile.",
                },
                "reason": {
                    "type": "string",
                    "description": "Lý do cleanup/delete/merge/rewrite.",
                },
            },
            "required": [
                "user_id",
                "section",
                "bullets",
                "expected_profile_hash",
                "reason",
            ],
        }

    async def execute(
        self,
        user_id: str,
        section: str,
        bullets: list[str],
        expected_profile_hash: str,
        reason: str,
    ) -> str:
        user_id = str(user_id or "").strip()
        section = str(section or "").strip()
        expected_profile_hash = str(expected_profile_hash or "").strip()
        reason = str(reason or "").strip()

        if not user_id:
            return "Lỗi: Thiếu user_id."
        if not user_id.isdigit():
            logger.warning("T3: invalid user_id for manage_user_profile: %s", user_id)
            return f"Lỗi: user_id '{user_id}' không hợp lệ. Phải là số ID Discord."
        if section not in SECTIONS:
            return f"Lỗi: section '{section}' không hợp lệ. Section hợp lệ: {', '.join(SECTIONS)}."
        if not isinstance(bullets, list):
            return "Lỗi: bullets phải là list chuỗi."
        if not expected_profile_hash:
            return "Lỗi: Thiếu expected_profile_hash từ profile hiện tại."
        if not reason:
            return "Lỗi: Thiếu reason cho thao tác curate hồ sơ."
        if not self.profile_store:
            return "Lỗi: MarkdownProfileStore (T3) chưa sẵn sàng."

        cleaned: list[str] = []
        for idx, bullet in enumerate(bullets, start=1):
            if not isinstance(bullet, str):
                return f"Lỗi: bullet #{idx} phải là chuỗi."
            value = bullet.strip()
            if not value:
                return f"Lỗi: bullet #{idx} không được trống."
            if "\n" in value or "\r" in value:
                return f"Lỗi: bullet #{idx} phải nằm trên một dòng."
            if value.startswith("- "):
                return f"Lỗi: bullet #{idx} không được có prefix '- '."
            cleaned.append(value)

        try:
            result = await self.profile_store.replace_section(
                user_id=user_id,
                section=section,
                bullets=cleaned,
                expected_profile_hash=expected_profile_hash,
            )
        except Exception as e:
            logger.error("T3: manage_user_profile failed: %s", e)
            raise ToolExecutionError(
                self.name,
                f"Lỗi hệ thống khi chỉnh hồ sơ: {e}",
                original_error=e,
            )

        if result.get("conflict"):
            return (
                "Conflict: hồ sơ đã thay đổi, không ghi. "
                f"Hash hiện tại: {result.get('profile_hash')}. "
                "Hãy đọc lại get_profile rồi gọi lại với expected_profile_hash mới."
            )

        action = "Đã thay" if result.get("written") else "Không thay đổi"
        logger.info(
            "T3: managed profile user=%s section=%s old=%s new=%s reason=%s",
            user_id,
            section,
            result.get("old_count"),
            result.get("new_count"),
            reason,
        )
        return (
            f"{action} section {section} của user {user_id}: "
            f"{result.get('old_count')} -> {result.get('new_count')} bullet. "
            f"Hash mới: {result.get('profile_hash')}."
        )

    def __repr__(self) -> str:
        return f"<ManageUserProfileTool: profile_store={self.profile_store is not None}>"
