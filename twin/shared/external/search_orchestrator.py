"""
SearchOrchestrator - Điều phối tìm kiếm T2 memory và Web search.

Phối hợp giữa:
- T2 memory search
- Web search (qua TavilyClient)

Fallback chain:
1. T2 memory → nếu có kết quả, trả về
2. Nếu T2 trống → Web search → nếu có kết quả, trả về
3. Nếu cả hai thất bại → thông báo lỗi graceful
"""

import logging
from typing import Optional, List, Any

from twin.shared.config.settings import Config
from twin.shared.external.tavily_client import SearchResult

logger = logging.getLogger(__name__)


class SearchOrchestrator:
    """
    Điều phối tìm kiếm T2 memory và Web search với fallback chain.

    Accepts memory_manager (T2Memory) and tavily_client (TavilyClient).
    All are optional for graceful degradation.

    Example:
        orchestrator = SearchOrchestrator(
            memory_manager=memory_manager,
            tavily_client=tavily_client,
        )
        result = await orchestrator.search(
            user_id="123",
            query="anime preferences",
            mode="auto",
        )
    """

    def __init__(
        self,
        memory_manager: Optional[Any] = None,
        tavily_client: Optional[Any] = None,
    ):
        self.memory = memory_manager
        self.tavily_client = tavily_client

        logger.info(
            f"SearchOrchestrator initialized - "
            f"memory_manager={memory_manager is not None}, "
            f"tavily_client={tavily_client is not None}"
        )

    async def search(
        self,
        user_id: str,
        query: str,
        mode: str = "auto",
        **kwargs,
    ) -> str:
        """
        Main entry point for coordinated search.

        Args:
            user_id: Discord user ID
            query: Search query string
            mode: Search mode - "auto" (default), "t2", or "web"
                - "auto": T2 → Web → error (fallback chain)
                - "t2": T2 memory only
                - "web": Web search only
            **kwargs: Additional parameters passed to underlying searches

        Returns:
            str: Formatted search results in Vietnamese for LLM consumption
        """
        if not query or not query.strip():
            return "Lỗi: Thiếu query tìm kiếm."

        query = query.strip()
        logger.info(f"🔍 SearchOrchestrator: query='{query[:50]}...', mode={mode}")

        if mode == "auto":
            return await self._search_auto(user_id, query, **kwargs)
        elif mode == "t2":
            return await self._search_t2_only(user_id, query, **kwargs)
        elif mode == "web":
            return await self._search_web_only(query, **kwargs)
        else:
            return f"Lỗi: Mode '{mode}' không hợp lệ. Dùng: auto, t2, hoặc web."

    async def _search_auto(self, user_id: str, query: str, **kwargs) -> str:
        """
        Fallback chain: T2 → Web → error.

        1. Try T2 memory (semantic search) — if results found, return
        2. If T2 empty → try Tavily web search — if results found, return
        3. If both fail → graceful error message
        """
        # Step 1: Try T2 memory
        logger.info("📚 SearchOrchestrator: Trying T2 memory search...")
        t2_results = await self._search_t2(user_id, query)
        if t2_results:
            logger.info(f"✅ SearchOrchestrator: T2 returned {len(t2_results)} results")
            return self._format_t2_results(t2_results, query)

        logger.info("📚 SearchOrchestrator: T2 returned no results, trying Web search...")

        # Step 2: Try Web search
        web_result = await self._search_web(query, **kwargs)
        if web_result:
            logger.info("✅ SearchOrchestrator: Web search returned results")
            return self._format_web_result(web_result, query)

        # Step 3: Both failed
        logger.warning(f"⚠️ SearchOrchestrator: Both T2 and Web search failed for '{query[:50]}'")
        return (
            f"Không tìm thấy thông tin nào về '{query}' trong ký ức hoặc trên web. "
            "Bạn thử hỏi với từ khóa khác nhé?"
        )

    async def _search_t2_only(self, user_id: str, query: str, **kwargs) -> str:
        """T2 memory search only."""
        logger.info("📚 SearchOrchestrator: T2-only search mode")
        t2_results = await self._search_t2(user_id, query)
        if t2_results:
            return self._format_t2_results(t2_results, query)
        return f"Không tìm thấy ký ức nào liên quan đến '{query}'."

    async def _search_web_only(self, query: str, **kwargs) -> str:
        """Web search only."""
        logger.info("🌐 SearchOrchestrator: Web-only search mode")
        web_result = await self._search_web(query, **kwargs)
        if web_result:
            return self._format_web_result(web_result, query)
        return f"Không tìm thấy kết quả web nào cho '{query}'."

    async def _search_t2(self, user_id: str, query: str) -> List[Any]:
        if not self.memory:
            logger.warning("SearchOrchestrator: memory_manager not available, skipping T2 search")
            return []

        try:
            results = await self.memory.search_pages(
                user_id=user_id,
                query=query,
                top_k=Config.SEARCH_TOP_K_SEMANTIC,
                min_relevance=Config.SEARCH_MIN_RELEVANCE,
            )
            return results or []
        except Exception as e:
            logger.error(f"SearchOrchestrator: T2 search error: {e}")
            return []

    async def _search_web(self, query: str, **kwargs) -> Optional[SearchResult]:
        """
        Search web using Tavily API.

        Args:
            query: Search query string
            **kwargs: Additional parameters passed to TavilyClient.search()

        Returns:
            SearchResult object, or None if search fails
        """
        if not self.tavily_client:
            logger.warning("SearchOrchestrator: tavily_client not available, skipping Web search")
            return None

        if not self.tavily_client.is_configured():
            logger.warning("SearchOrchestrator: Tavily not configured, skipping Web search")
            return None

        try:
            raw_result = await self.tavily_client.search(query, **kwargs)

            # Convert raw Tavily response to SearchResult
            answer = raw_result.get("answer")
            results = raw_result.get("results", [])

            sources = []
            for r in results:
                sources.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("content", ""),
                    "score": r.get("score", 0),
                })

            return SearchResult(
                query=query,
                answer=answer,
                sources=sources,
                topic=raw_result.get("query_context", {}).get("topic") if raw_result.get("query_context") else None,
                time_range=None,
                result_count=len(sources),
            )

        except Exception as e:
            logger.error(f"SearchOrchestrator: Web search error: {e}")
            return None

    def merge_results(
        self,
        t2_results: List[Any],
        web_result: Optional[SearchResult],
    ) -> str:
        """
        Merge T2 and Web results with T2 first.

        This is the public API for combining results from both sources.
        T2 results are listed first, followed Web search sources.

        Args:
            t2_results: List of T2Page objects
            web_result: Optional SearchResult from Tavily

        Returns:
            str: Merged formatted results in Vietnamese
        """
        lines = []

        if t2_results:
            lines.append("📚 **Kết quả từ T2 Memory:**")
            lines.append(self._format_t2_results(t2_results, ""))
            lines.append("")

        if web_result and web_result.sources:
            lines.append("🌐 **Kết quả từ Web Search:**")
            lines.append(self._format_web_sources(web_result))

        return "\n".join(lines)

    def _format_t2_results(self, results: List[Any], query: str) -> str:
        """Format T2 results for LLM consumption."""
        lines = [f"Đã tìm thấy {len(results)} kết quả trong T2 Memory cho '{query}':\n"]

        for i, page in enumerate(results, 1):
            lines.append(f"{i}. **{page.canonical_topic}** (Category: {page.category})")
            lines.append(f"   Summary: {page.current_summary}")

            if page.key_points:
                lines.append("   Key Points:")
                for point in page.key_points[:5]:
                    lines.append(f"   - {point}")

            lines.append(f"   ⭐ Importance: {page.importance}/5")
            lines.append("")

        return "\n".join(lines)

    def _format_web_result(self, result: SearchResult, query: str) -> str:
        """Format a single web search result for LLM consumption."""
        lines = [f"🌐 Kết quả Web Search cho '{query}':\n"]

        if result.answer:
            lines.append(f"**Trả lời:** {result.answer}\n")

        if result.sources:
            lines.append(f"**Nguồn ({result.result_count} kết quả):**\n")
            for i, source in enumerate(result.sources, 1):
                lines.append(f"{i}. **{source['title']}**")
                lines.append(f"   URL: {source['url']}")
                if source.get("content"):
                    lines.append(f"   Nội dung: {source['content'][:200]}")
                lines.append("")

        return "\n".join(lines)

    def _format_web_sources(self, result: SearchResult) -> str:
        """Format web sources for merged results display."""
        lines = []

        if result.answer:
            lines.append(f"**Trả lời:** {result.answer}\n")

        if result.sources:
            for i, source in enumerate(result.sources, 1):
                lines.append(f"{i}. **{source['title']}**")
                lines.append(f"   URL: {source['url']}")
                if source.get("content"):
                    lines.append(f"   Nội dung: {source['content'][:200]}")
                lines.append("")

        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"<SearchOrchestrator: "
            f"memory={self.memory is not None}, "
            f"tavily={self.tavily_client is not None}>"
        )
