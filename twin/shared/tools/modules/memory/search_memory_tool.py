"""SearchMemoryTool - query T2 timeline memory."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from twin.shared.config.settings import Config
from twin.shared.tools.registry.base import BaseTool, ToolExecutionError

logger = logging.getLogger(__name__)

_VALID_TOOL_MODES = {"auto", "semantic", "time", "recent", "hybrid"}
_MAX_LIMIT = 20


class SearchMemoryTool(BaseTool):
    """Tool for querying Redis Stack backed T2 timeline memory."""

    def __init__(
        self,
        timeline_summary_store: Optional[Any] = None,
        embedding_service: Optional[Any] = None,
    ):
        self.timeline_summary_store = timeline_summary_store
        self.embedding_service = embedding_service

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
                    "enum": ["auto", "semantic", "time", "recent", "hybrid"],
                    "default": "auto",
                    "description": "auto, semantic, time, recent, hybrid.",
                },
                "query": {
                    "type": "string",
                    "description": "Truy vấn semantic.",
                },
                "topic": {
                    "type": "string",
                    "description": "Lọc theo topic slug (ví dụ: work, interest). Tùy chọn.",
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
        topic: Optional[str] = None,
        hours: Optional[int] = 24,
        days: Optional[int] = None,
        limit: int = 5,
    ) -> str:
        user_id = str(user_id or "").strip()
        mode = (mode or "auto").strip()
        query = (query or "").strip() or None
        topic = (topic or "").strip() or None

        if not user_id:
            return "Lỗi: Thiếu user_id."

        if not user_id.isdigit():
            logger.warning("T2: invalid user_id for search_memory: %s", user_id)
            return f"Lỗi: user_id '{user_id}' không hợp lệ. user_id phải là số ID của Discord user."

        if mode not in _VALID_TOOL_MODES:
            return f"Lỗi: mode '{mode}' không hợp lệ. Mode hợp lệ: {', '.join(sorted(_VALID_TOOL_MODES))}."

        if self.timeline_summary_store is None:
            return "Lỗi: timeline_summary_store chưa được cấu hình."

        limit = self._bounded_limit(limit)
        resolved_mode = mode
        if resolved_mode == "auto":
            resolved_mode = "hybrid" if query else "recent"

        if resolved_mode in ("semantic", "hybrid"):
            if not query:
                return "Lỗi: Chế độ semantic/hybrid yêu cầu tham số 'query'."
            if self.embedding_service is None:
                return "Lỗi: embedding_service chưa được cấu hình."
            try:
                embedding = await self.embedding_service.get_embedding(f"{Config.EMBEDDING_QUERY_PREFIX}{query}")
                memories = await self.timeline_summary_store.search(
                    user_id=user_id,
                    query_embedding=embedding,
                    limit=limit,
                    query_text=query if resolved_mode == "hybrid" else None,
                    topic_filter=topic,
                )
            except Exception as e:
                logger.error("SearchMemoryTool: semantic search failed: %s", e, exc_info=True)
                return f"Lỗi khi tìm kiếm ký ức: {e}"
        else:
            try:
                memories = await self.timeline_summary_store.get_recent(
                    user_id=user_id,
                    limit=limit,
                )
            except Exception as e:
                logger.error("SearchMemoryTool: get_recent failed: %s", e, exc_info=True)
                return f"Lỗi khi lấy ký ức gần đây: {e}"

        return self._format_memories(memories)

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
            content = (
                SearchMemoryTool._field(memory, "summary")
                or SearchMemoryTool._field(memory, "content")
                or str(memory)
            )
            content = str(content).strip()
            topic_val = SearchMemoryTool._field(memory, "topic")
            topic_display = SearchMemoryTool._field(memory, "topic_display")
            label = topic_display or topic_val
            if label:
                lines.append(f"{index}. [{label}] {content}")
            else:
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
        for field_name in ("memory_id", "summary_id", "speaker"):
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
            try:
                ts = float(created_at)
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                metadata.append(f"created_at={dt.isoformat()}")
            except (ValueError, TypeError):
                metadata.append(f"created_at={created_at}")

        return metadata

    def __repr__(self) -> str:
        return f"<SearchMemoryTool: timeline_summary_store={self.timeline_summary_store is not None}>"
