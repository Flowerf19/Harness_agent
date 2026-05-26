"""SearchMemoryTool - query Redis-backed T2 memory."""

import logging
from typing import Dict, Any, Optional

from twin.shared.tools.registry.base import BaseTool, ToolExecutionError

logger = logging.getLogger(__name__)


class SearchMemoryTool(BaseTool):
    """Tool cho Bé Bảy tìm ký ức trong T2 Wiki Pages."""

    def __init__(self, memory_manager: Optional[Any] = None):
        self.memory_manager = memory_manager

    @property
    def name(self) -> str:
        return "search_memory"

    @property
    def description(self) -> str:
        return "Tìm ký ức trong T2 memory. Chi tiết cách dùng xem TOOL.md."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "Discord user ID (số) của user đang chat. VD: '726302130318868500'"
                },
                "mode": {
                    "type": "string",
                    "enum": ["auto", "semantic", "time", "topic", "topic_timeline", "related_context", "recent"],
                    "default": "auto",
                    "description": "Search mode. Use time for explicit dates/ranges; use topic_timeline for ordered topic history."
                },
                "query": {
                    "type": "string",
                    "description": "Query for semantic search (used when mode='semantic'). VD: 'sở thích', 'anime'"
                },
                "days": {
                    "type": "integer",
                    "default": 7,
                    "description": "Days to look back (used when mode='time'). VD: 7 for last week"
                },
                "start_date": {
                    "type": "string",
                    "description": "Inclusive YYYY-MM-DD start date for time/topic_timeline search."
                },
                "end_date": {
                    "type": "string",
                    "description": "Inclusive YYYY-MM-DD end date for time/topic_timeline search."
                },
                "topic": {
                    "type": "string",
                    "description": "Topic keyword to search (used when mode='topic'). VD: 'anime', 'game'"
                },
                "limit": {
                    "type": "integer",
                    "default": 5,
                    "description": "Maximum memories to return."
                },
                "context_depth": {
                    "type": "integer",
                    "default": 1,
                    "description": "Relationship traversal depth for related_context."
                },
                "max_related_chunks": {
                    "type": "integer",
                    "default": 5,
                    "description": "Maximum chunks to follow for related_context."
                }
            },
            "required": ["user_id"]
        }

    async def execute(
        self,
        user_id: str,
        mode: str = "auto",
        query: Optional[str] = None,
        days: Optional[int] = 7,
        topic: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 5,
        context_depth: int = 1,
        max_related_chunks: int = 5,
    ) -> str:
        if not user_id:
            return "Lỗi: Thiếu user_id."

        if not user_id.isdigit():
            logger.warning(f"Invalid user_id: {user_id}")
            return f"Lỗi: user_id '{user_id}' không hợp lệ. user_id phải là số ID của Discord user."

        if not self.memory_manager:
            return "Lỗi: Hệ thống Wiki Memory chưa sẵn sàng."

        try:
            return await self.memory_manager.search(
                user_id=user_id,
                mode=mode,
                query=query,
                days=days,
                topic=topic,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
                context_depth=context_depth,
                max_related_chunks=max_related_chunks,
            )
        except Exception as e:
            logger.error(f"SearchMemoryTool failed: {e}")
            raise ToolExecutionError(self.name, f"Lỗi khi tìm kiếm: {e}", original_error=e)

    def __repr__(self) -> str:
        return f"<SearchMemoryTool: manager={self.memory_manager is not None}>"
