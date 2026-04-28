"""
SearchMemoryTool - Query Wiki Pages (T2).

Tool for searching consolidated topics from Wiki Pages in Qdrant.
Uses WikiStorage for semantic search with embeddings.
"""

import logging
from typing import Dict, Any, Optional, List

import config
from src.services.tools.base_tool import BaseTool, ToolExecutionError

logger = logging.getLogger(__name__)


class SearchMemoryTool(BaseTool):
    """
    Tool for searching Wiki Pages (T2 consolidated memory).

    Searches consolidated topics, preferences, and facts from Wiki Pages.
    Uses semantic search with LocalEmbeddingService.

    Attributes:
        wiki_storage: WikiStorage instance for T2 Wiki Pages
        embedding_service: LocalEmbeddingService for query embedding

    Example:
        tool = SearchMemoryTool(wiki_storage, embedding_service)
        result = await tool.execute(user_id="123", query="anime preferences")
    """

    def __init__(
        self,
        wiki_storage: Optional[Any] = None,
        embedding_service: Optional[Any] = None,
    ):
        """
        Initialize SearchMemoryTool.

        Args:
            wiki_storage: WikiStorage for T2 Wiki Pages search
            embedding_service: LocalEmbeddingService for query embedding
        """
        self.wiki_storage = wiki_storage
        self.embedding_service = embedding_service
        logger.info(
            f"SearchMemoryTool initialized with "
            f"wiki_storage={wiki_storage is not None}, "
            f"embedding_service={embedding_service is not None}"
        )

    # ==========================================
    # BASE TOOL PROPERTIES
    # ==========================================

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

    # ==========================================
    # EXECUTION
    # ==========================================

    async def execute(
        self,
        user_id: str,
        mode: str = "semantic",
        query: Optional[str] = None,
        days: int = 7,
        topic: Optional[str] = None,
    ) -> str:
        """
        Search Wiki Pages for past context.

        Args:
            user_id: Discord user ID (must be numeric)
            mode: Search mode - "semantic", "time", or "topic"
            query: Search query (for semantic mode)
            days: Days to look back (for time mode)
            topic: Topic keyword (for topic mode)

        Returns:
            str: Search results formatted for LLM consumption
        """
        # Validate user_id
        if not user_id:
            return "Lỗi: Thiếu user_id."

        if not user_id.isdigit():
            logger.warning(f"⚠️ Invalid user_id: {user_id} - không phải số")
            return f"Lỗi: user_id '{user_id}' không hợp lệ. user_id phải là số ID của Discord user."

        # Check if wiki_storage is available
        if not self.wiki_storage:
            return "Lỗi: Hệ thống Wiki Memory chưa sẵn sàng."

        # Dispatch based on mode
        if mode == "semantic":
            return await self._search_semantic(user_id, query)
        elif mode == "time":
            return await self._search_by_time(user_id, days)
        elif mode == "topic":
            return await self._search_by_topic(user_id, topic)
        else:
            return f"Lỗi: Mode '{mode}' không hợp lệ. Dùng: semantic, time, hoặc topic."

    async def _search_semantic(self, user_id: str, query: Optional[str]) -> str:
        """Semantic search using embeddings."""
        if not query:
            return "Lỗi: Mode 'semantic' cần parameter 'query'."

        if not self.embedding_service:
            return "Lỗi: Embedding service chưa sẵn sàng cho semantic search."

        try:
            query_vector = await self.embedding_service.get_embedding(query)
            if not query_vector:
                return "Lỗi: Không thể tạo embedding cho query."

            results = await self.wiki_storage.search_similar(
                user_id=user_id,
                query_vector=query_vector,
                top_k=config.SEARCH_TOP_K_SEMANTIC,
                min_relevance=config.SEARCH_MIN_RELEVANCE,
            )

            if not results:
                return f"Không tìm thấy ký ức nào liên quan đến '{query}'."

            return self._format_results(results, f"semantic: {query}")

        except Exception as e:
            logger.error(f"Lỗi khi tìm kiếm semantic: {e}")
            raise ToolExecutionError(self.name, f"Lỗi khi tìm kiếm: {e}", original_error=e)

    async def _search_by_time(self, user_id: str, days: int) -> str:
        """Time-based search - recent updates."""
        try:
            results = await self.wiki_storage.search_by_time(
                user_id=user_id,
                days=days,
                top_k=config.SEARCH_TOP_K_TIME,
            )

            if not results:
                return f"Không tìm thấy ký ức nào được cập nhật trong {days} ngày qua."

            return self._format_results(results, f"time: last {days} days", show_time=True)

        except Exception as e:
            logger.error(f"Lỗi khi tìm kiếm theo thời gian: {e}")
            raise ToolExecutionError(self.name, f"Lỗi khi tìm kiếm: {e}", original_error=e)

    async def _search_by_topic(self, user_id: str, topic: Optional[str]) -> str:
        """Topic keyword search."""
        if not topic:
            return "Lỗi: Mode 'topic' cần parameter 'topic'."

        try:
            results = await self.wiki_storage.search_by_topic(
                user_id=user_id,
                topic_keyword=topic,
                top_k=config.SEARCH_TOP_K_TOPIC,
            )

            if not results:
                return f"Không tìm thấy ký ức nào với topic chứa '{topic}'."

            return self._format_results(results, f"topic: {topic}", show_importance=True)

        except Exception as e:
            logger.error(f"Lỗi khi tìm kiếm theo topic: {e}")
            raise ToolExecutionError(self.name, f"Lỗi khi tìm kiếm: {e}", original_error=e)

    def _format_results(
        self,
        results: List[Any],
        search_context: str,
        show_time: bool = False,
        show_importance: bool = False,
    ) -> str:
        """
        Format Wiki Pages results for LLM consumption.

        Args:
            results: List of WikiPagePayload objects
            search_context: Description of the search context
            show_time: Whether to show last_updated
            show_importance: Whether to show importance for all results

        Returns:
            str: Formatted results string
        """
        lines = [f"Đã tìm thấy {len(results)} Wiki Pages ({search_context}):\n"]

        for i, page in enumerate(results, 1):
            lines.append(f"\n{i}. **{page.canonical_topic}** (Category: {page.category})")
            lines.append(f"   Summary: {page.current_summary}")

            if page.key_points:
                lines.append("   Key Points:")
                for point in page.key_points[:5]:
                    lines.append(f"   - {point}")

            if show_time:
                lines.append(f"   📅 Last updated: {page.last_updated.strftime('%Y-%m-%d %H:%M')}")

            if show_importance or page.importance >= 4:
                lines.append(f"   ⭐ Importance: {page.importance}/5")

        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"<SearchMemoryTool: "
            f"wiki_storage={self.wiki_storage is not None}, "
            f"embedding={self.embedding_service is not None}>"
        )