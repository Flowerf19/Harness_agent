"""SearchMemoryTool - query T2 timeline memory."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from twin.shared.tools.registry.base import BaseTool, ToolExecutionError

logger = logging.getLogger(__name__)

_VALID_TOOL_MODES = {"auto", "semantic", "time", "topic", "recent"}
_MAX_LIMIT = 20


class SearchMemoryTool(BaseTool):
    """Tool for querying Redis Stack backed T2 timeline memory."""

    def __init__(self, timeline_search: Optional[Any] = None):
        self.timeline_search = timeline_search

    @property
    def name(self) -> str:
        return "search_memory"

    @property
    def description(self) -> str:
        return (
            "Tìm ký ức T2 timeline. Dùng semantic cho nội dung, topic cho topic_id, "
            "time/recent cho ký ức gần đây."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "Discord user ID (số) của user đang chat.",
                },
                "mode": {
                    "type": "string",
                    "enum": ["auto", "semantic", "time", "topic", "recent"],
                    "default": "auto",
                    "description": "auto tự chọn; semantic cần query; topic cần topic_id; time/recent dùng hours/days.",
                },
                "query": {
                    "type": "string",
                    "description": "Query cho semantic search. VD: 'sở thích anime'.",
                },
                "topic_id": {
                    "type": "string",
                    "description": "T2 topic_id để search theo topic.",
                },
                "topic": {
                    "type": "string",
                    "description": "Alias tương thích cũ cho topic_id.",
                },
                "hours": {
                    "type": "integer",
                    "default": 24,
                    "description": "Số giờ nhìn lại cho recent/time.",
                },
                "days": {
                    "type": "integer",
                    "description": "Alias cho time: days * 24 giờ.",
                },
                "limit": {
                    "type": "integer",
                    "default": 5,
                    "description": f"Số memory tối đa, cap {_MAX_LIMIT}.",
                },
                "exclude_superseded": {
                    "type": "boolean",
                    "default": True,
                    "description": "Loại memory đã bị supersede khi mode hỗ trợ.",
                },
            },
            "required": ["user_id"],
        }

    async def execute(
        self,
        user_id: str,
        mode: str = "auto",
        query: Optional[str] = None,
        topic_id: Optional[str] = None,
        topic: Optional[str] = None,
        hours: Optional[int] = 24,
        days: Optional[int] = None,
        limit: int = 5,
        exclude_superseded: bool = True,
    ) -> str:
        user_id = str(user_id or "").strip()
        mode = (mode or "auto").strip()
        query = (query or "").strip() or None
        topic_key = (topic_id or topic or "").strip() or None

        if not user_id:
            return "Lỗi: Thiếu user_id."

        if not user_id.isdigit():
            logger.warning("T2: invalid user_id for search_memory: %s", user_id)
            return f"Lỗi: user_id '{user_id}' không hợp lệ. user_id phải là số ID của Discord user."

        if mode not in _VALID_TOOL_MODES:
            return f"Lỗi: mode '{mode}' không hợp lệ. Mode hợp lệ: {', '.join(sorted(_VALID_TOOL_MODES))}."

        if not self.timeline_search:
            return "Lỗi: TimelineSearch chưa sẵn sàng."

        timeline_mode = self._timeline_mode(mode)
        if timeline_mode == "semantic" and not query:
            return "Lỗi: mode semantic cần query."
        if timeline_mode == "by_topic" and not topic_key:
            return "Lỗi: mode topic cần topic_id."

        try:
            memories = await self.timeline_search.search(
                user_id=user_id,
                query=query,
                mode=timeline_mode,
                limit=self._bounded_limit(limit),
                topic_id=topic_key,
                hours=self._resolve_hours(mode, hours, days),
                exclude_superseded=exclude_superseded,
            )
            return self._format_memories(memories)
        except Exception as e:
            logger.error("T2: SearchMemoryTool failed: %s", e)
            raise ToolExecutionError(self.name, f"Lỗi khi tìm kiếm: {e}", original_error=e)

    @staticmethod
    def _timeline_mode(mode: str) -> str:
        if mode == "topic":
            return "by_topic"
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
        for field_name in ("memory_id", "speaker", "change_type"):
            value = SearchMemoryTool._field(memory, field_name)
            if value:
                metadata.append(f"{field_name}={value}")

        for field_name in ("topic_ids", "catalogs"):
            value = SearchMemoryTool._field(memory, field_name)
            if value:
                metadata.append(f"{field_name}={','.join(value)}")

        created_at = SearchMemoryTool._field(memory, "created_at")
        if isinstance(created_at, datetime):
            metadata.append(f"created_at={created_at.isoformat()}")
        elif created_at:
            metadata.append(f"created_at={created_at}")

        superseded_by = SearchMemoryTool._field(memory, "superseded_by")
        if superseded_by:
            metadata.append(f"superseded_by={superseded_by}")
        return metadata

    def __repr__(self) -> str:
        return f"<SearchMemoryTool: timeline_search={self.timeline_search is not None}>"
