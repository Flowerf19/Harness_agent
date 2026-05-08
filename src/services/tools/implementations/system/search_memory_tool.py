"""
SearchMemoryTool - Query Wiki Pages (T2).

Thin wrapper over EpisodicMemoryManager.
LLM calls this tool → delegates to memory_manager.search().
"""

import logging
from typing import Dict, Any, Optional

from src.services.tools.base_tool import BaseTool, ToolExecutionError

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
        return "Tìm ký ức trong Wiki Pages (T2). Chi tiết cách dùng xem TOOL.md."

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
                    "enum": ["semantic", "time", "topic"],
                    "default": "semantic",
                    "description": "Search mode: semantic (query content), time (recent updates), topic (keyword match)"
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
                "topic": {
                    "type": "string",
                    "description": "Topic keyword to search (used when mode='topic'). VD: 'anime', 'game'"
                }
            },
            "required": ["user_id"]
        }

    async def execute(
        self,
        user_id: str,
        mode: str = "semantic",
        query: Optional[str] = None,
        days: int = 7,
        topic: Optional[str] = None,
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
            )
        except Exception as e:
            logger.error(f"SearchMemoryTool failed: {e}")
            raise ToolExecutionError(self.name, f"Lỗi khi tìm kiếm: {e}", original_error=e)

    def __repr__(self) -> str:
        return f"<SearchMemoryTool: manager={self.memory_manager is not None}>"
