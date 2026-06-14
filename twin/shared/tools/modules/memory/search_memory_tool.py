"""SearchMemoryTool - query T2 timeline memory."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from twin.shared.tools.registry.base import BaseTool, ToolExecutionError

logger = logging.getLogger(__name__)

_VALID_TOOL_MODES = {"auto", "semantic", "time", "recent"}
_MAX_LIMIT = 20


class SearchMemoryTool(BaseTool):
    """Tool for querying Redis Stack backed T2 timeline memory."""

    def __init__(self, timeline_search: Optional[Any] = None):
        self.timeline_search = timeline_search

    @property
    def name(self) -> str:
        return "search_memory"

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "Discord user ID.",
                },
                "mode": {
                    "type": "string",
                    "enum": ["auto", "semantic", "time", "recent"],
                    "default": "auto",
                    "description": "auto, semantic, time, recent.",
                },
                "query": {
                    "type": "string",
                    "description": "Truy vấn semantic.",
                },
                "hours": {
                    "type": "integer",
                    "default": 24,
                    "description": "Số giờ nhìn lại.",
                },
                "days": {
                    "type": "integer",
                    "description": "Số ngày nhìn lại.",
                },
                "limit": {
                    "type": "integer",
                    "default": 5,
                    "description": f"Số kết quả, tối đa {_MAX_LIMIT}.",
                },
            },
            "required": ["user_id"],
        }

    async def execute(
        self,
        user_id: str,
        mode: str = "auto",
        query: Optional[str] = None,
        hours: Optional[int] = 24,
        days: Optional[int] = None,
        limit: int = 5,
    ) -> str:
        user_id = str(user_id or "").strip()
        mode = (mode or "auto").strip()
        query = (query or "").strip() or None

        if not user_id:
            return "Lỗi: Thiếu user_id."

        if not user_id.isdigit():
            logger.warning("T2: invalid user_id for search_memory: %s", user_id)
            return f"Lỗi: user_id '{user_id}' không hợp lệ. user_id phải là số ID của Discord user."

        if mode not in _VALID_TOOL_MODES:
            return f"Lỗi: mode '{mode}' không hợp lệ. Mode hợp lệ: {', '.join(sorted(_VALID_TOOL_MODES))}."

        return "Lỗi: T2 search đã bị vô hiệu hóa — đang chờ cập nhật TimelineSummaryStore."

    @staticmethod
    def _timeline_mode(mode: str) -> str:
        if mode == "time":
            return "recent"
        return mode

    @staticmethod
    def _bounded_limit(limit: int) -> int:
        try:
            value = int(limit)
        except (TypeError, ValueError):
            value = 5
        return max(1, min(value, _MAX_LIMIT))

    @staticmethod
    def _resolve_hours(mode: str, hours: Optional[int], days: Optional[int]) -> int:
        if mode == "time" and days is not None:
            try:
                return max(1, int(days)) * 24
            except (TypeError, ValueError):
                return 24
        try:
            return max(1, int(hours if hours is not None else 24))
        except (TypeError, ValueError):
            return 24

    @staticmethod
    def _format_memories(memories: Any) -> str:
        if isinstance(memories, str):
            return memories
        if not memories:
            return "Không tìm thấy ký ức phù hợp."

        lines = [f"Tìm thấy {len(memories)} ký ức:"]
        for index, memory in enumerate(memories, start=1):
            content = str(SearchMemoryTool._field(memory, "content", str(memory))).strip()
            lines.append(f"{index}. {content}")
            metadata = SearchMemoryTool._metadata(memory)
            if metadata:
                lines.append(f"   ({'; '.join(metadata)})")
        return "\n".join(lines)

    @staticmethod
    def _field(memory: Any, field_name: str, default: Any = None) -> Any:
        if isinstance(memory, dict):
            return memory.get(field_name, default)
        return getattr(memory, field_name, default)

    @staticmethod
    def _metadata(memory: Any) -> list[str]:
        metadata: list[str] = []
        for field_name in ("memory_id", "speaker"):
            value = SearchMemoryTool._field(memory, field_name)
            if value:
                metadata.append(f"{field_name}={value}")

        catalogs = SearchMemoryTool._field(memory, "catalogs")
        if catalogs:
            metadata.append(f"catalogs={','.join(catalogs)}")

        created_at = SearchMemoryTool._field(memory, "created_at")
        if isinstance(created_at, datetime):
            metadata.append(f"created_at={created_at.isoformat()}")
        elif created_at:
            metadata.append(f"created_at={created_at}")

        return metadata

    def __repr__(self) -> str:
        return f"<SearchMemoryTool: timeline_search={self.timeline_search is not None}>"
