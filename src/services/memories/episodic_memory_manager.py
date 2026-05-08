"""EpisodicMemoryManager - Facade for T2 Wiki Pages.

Gộp embedding_service + wiki_storage thành một trạm quản lý tập trung.
Dùng chung cho cả SearchMemoryTool (Bé Bảy) và EvernightAgent (background).

Embedding model chỉ load khi có request đầu tiên (lazy).
"""

import logging
from datetime import datetime, timezone
from typing import Any, List, Optional

from src.config.settings import Config

logger = logging.getLogger(__name__)


class EpisodicMemoryManager:
    """
    Facade tập trung cho T2 Episodic Memory.

    Gom embedding + Qdrant storage vào một cổng duy nhất.
    - SearchMemoryTool gọi search()
    - EvernightAgent gọi embed_page(), refresh_access()
    """

    def __init__(self, wiki_storage: Any, embedding_service: Any):
        self.storage = wiki_storage
        self._embedding = embedding_service
        self._embedding_ready = False

    async def _ensure_embedding(self):
        if not self._embedding_ready:
            await self._embedding.initialize()
            self._embedding_ready = True

    async def search_pages(
        self,
        user_id: str,
        query: str,
        top_k: int = 5,
        min_relevance: float = 0.5,
    ) -> List[Any]:
        """
        Semantic search trả về raw WikiPagePayload list.
        Dùng bởi SearchOrchestrator để tự format + merge với Web results.
        """
        await self._ensure_embedding()

        query_vector = await self._embedding.get_embedding(query)
        if not query_vector:
            return []

        return await self.storage.search_similar(
            user_id=user_id,
            query_vector=query_vector,
            top_k=top_k,
            min_relevance=min_relevance,
        )

    async def search(
        self,
        user_id: str,
        mode: str = "semantic",
        query: Optional[str] = None,
        days: int = 7,
        topic: Optional[str] = None,
    ) -> str:
        if mode == "semantic":
            return await self._search_semantic(user_id, query)
        elif mode == "time":
            return await self._search_by_time(user_id, days)
        elif mode == "topic":
            return await self._search_by_topic(user_id, topic)
        else:
            return f"Lỗi: Mode '{mode}' không hợp lệ. Dùng: semantic, time, hoặc topic."

    async def _search_semantic(self, user_id: str, query: Optional[str]) -> str:
        if not query:
            return "Lỗi: Mode 'semantic' cần parameter 'query'."

        await self._ensure_embedding()

        try:
            query_vector = await self._embedding.get_embedding(query)
            if not query_vector:
                return "Lỗi: Không thể tạo embedding cho query."

            results = await self.storage.search_similar(
                user_id=user_id,
                query_vector=query_vector,
                top_k=Config.SEARCH_TOP_K_SEMANTIC,
                min_relevance=Config.SEARCH_MIN_RELEVANCE,
            )

            if not results:
                return f"Không tìm thấy ký ức nào liên quan đến '{query}'."

            return self._format_results(results, f"semantic: {query}")

        except Exception as e:
            logger.error(f"Lỗi khi tìm kiếm semantic: {e}")
            return f"Lỗi khi tìm kiếm semantic: {e}"

    async def _search_by_time(self, user_id: str, days: int) -> str:
        try:
            results = await self.storage.search_by_time(
                user_id=user_id,
                days=days,
                top_k=Config.SEARCH_TOP_K_TIME,
            )

            if not results:
                return f"Không tìm thấy ký ức nào được cập nhật trong {days} ngày qua."

            return self._format_results(results, f"time: last {days} days", show_time=True)

        except Exception as e:
            logger.error(f"Lỗi khi tìm kiếm theo thời gian: {e}")
            return f"Lỗi khi tìm kiếm theo thời gian: {e}"

    async def _search_by_topic(self, user_id: str, topic: Optional[str]) -> str:
        if not topic:
            return "Lỗi: Mode 'topic' cần parameter 'topic'."

        try:
            results = await self.storage.search_by_topic(
                user_id=user_id,
                topic_keyword=topic,
                top_k=Config.SEARCH_TOP_K_TOPIC,
            )

            if not results:
                return f"Không tìm thấy ký ức nào với topic chứa '{topic}'."

            return self._format_results(results, f"topic: {topic}", show_importance=True)

        except Exception as e:
            logger.error(f"Lỗi khi tìm kiếm theo topic: {e}")
            return f"Lỗi khi tìm kiếm theo topic: {e}"

    async def embed_page(self, page: Any) -> bool:
        """
        Tạo embedding cho WikiPagePayload và upsert vào Qdrant.

        Dùng bởi EvernightAgent sau khi merge/create page.
        Embedding model được load lazy khi gọi lần đầu.
        """
        await self._ensure_embedding()

        search_content = self._build_search_content(page)
        embedding = await self._embedding.get_embedding(search_content)
        if not embedding:
            logger.warning(f"Failed to embed page '{page.canonical_topic}'")
            return False

        page.embedding = embedding
        return await self.storage.upsert_page(page)

    async def lookup_by_page_id(self, page_id: str):
        """Lookup WikiPage by page_id. Delegate to storage."""
        return await self.storage.lookup_by_page_id(page_id)

    async def refresh_access(self, page_id: str) -> None:
        await self.storage.refresh_access(page_id)

    async def clear_embedding_cache(self):
        """Xóa cache embedding nội bộ (tối đa 100 entries)."""
        if self._embedding_ready:
            self._embedding._cache.clear()

    def _build_search_content(self, page: Any) -> str:
        parts = [page.canonical_topic, page.current_summary]
        if page.key_points:
            parts.extend(page.key_points)
        return "\n".join(parts)

    def _format_results(
        self,
        results: List[Any],
        search_context: str,
        show_time: bool = False,
        show_importance: bool = False,
    ) -> str:
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
