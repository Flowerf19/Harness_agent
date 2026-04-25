"""
SearchMemoryTool - Query Wiki Pages (T2).

Tool for searching consolidated topics from Wiki Pages in Qdrant.
Uses WikiStorage for semantic search with embeddings.
"""

import logging
from typing import Dict, Any, Optional, List

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
        return (
            "Tìm kiếm ký ức của user từ Wiki Pages (T2). "
            "Dùng khi user nhắc chuyện quá khứ, hỏi về sở thích/sự kiện cũ, "
            "hoặc cần context từ lịch sử hội thoại."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "Discord user ID (số) của user đang chat. VD: '726302130318868500'"
                },
                "query": {
                    "type": "string",
                    "description": "Từ khóa hoặc câu hỏi để tìm kiếm trong ký ức. VD: 'sở thích', 'anime', 'chuyện hôm qua'"
                }
            },
            "required": ["user_id", "query"]
        }

    # ==========================================
    # EXECUTION
    # ==========================================

    async def execute(self, user_id: str, query: str) -> str:
        """
        Search Wiki Pages for past context.

        Args:
            user_id: Discord user ID (must be numeric)
            query: Search query string

        Returns:
            str: Search results formatted for LLM consumption
        """
        # Validate inputs
        if not user_id or not query:
            return "Lỗi: Thiếu user_id hoặc query."

        # Validate user_id format (Discord ID must be numeric)
        if not user_id.isdigit():
            logger.warning(f"⚠️ Invalid user_id: {user_id} - không phải số")
            return f"Lỗi: user_id '{user_id}' không hợp lệ. user_id phải là số ID của Discord user."

        # Check if wiki_storage is available
        if not self.wiki_storage:
            return "Lỗi: Hệ thống Wiki Memory chưa sẵn sàng."

        # Check if embedding_service is available
        if not self.embedding_service:
            return "Lỗi: Embedding service chưa sẵn sàng."

        # Execute search
        try:
            # Generate embedding for query
            query_vector = await self.embedding_service.get_embedding(query)
            if not query_vector:
                return "Lỗi: Không thể tạo embedding cho query."

            # Search Wiki Pages
            results = await self.wiki_storage.search_similar(
                user_id=user_id,
                query_vector=query_vector,
                top_k=5,
                min_relevance=0.3,
            )

            if not results:
                return f"Không tìm thấy ký ức nào liên quan đến '{query}'."

            # Format results for LLM
            formatted_results = self._format_results(results, query)

            return formatted_results

        except Exception as e:
            logger.error(f"Lỗi khi tìm kiếm Wiki Pages: {e}")
            raise ToolExecutionError(self.name, f"Lỗi khi tìm kiếm ký ức: {e}", original_error=e)

    def _format_results(self, results: List[Any], query: str) -> str:
        """
        Format Wiki Pages results for LLM consumption.

        Args:
            results: List of WikiPagePayload objects
            query: Original search query

        Returns:
            str: Formatted results string
        """
        lines = [f"Đã tìm thấy {len(results)} Wiki Pages liên quan đến '{query}':\n"]

        for i, page in enumerate(results, 1):
            lines.append(f"\n{i}. **{page.canonical_topic}** (Category: {page.category})")
            lines.append(f"   Summary: {page.current_summary}")

            if page.key_points:
                lines.append("   Key Points:")
                for point in page.key_points[:5]:
                    lines.append(f"   - {point}")

            # Include importance if high
            if page.importance >= 4:
                lines.append(f"   ⭐ Importance: {page.importance}/5")

        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"<SearchMemoryTool: "
            f"wiki_storage={self.wiki_storage is not None}, "
            f"embedding={self.embedding_service is not None}>"
        )