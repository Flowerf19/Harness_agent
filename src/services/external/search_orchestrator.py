"""
SearchOrchestrator - Điều phối tìm kiếm Wiki memory và Web search.

Phối hợp giữa:
- Wiki memory search (semantic, qua WikiStorage + LocalEmbeddingService)
- Web search (qua TavilyClient)

Fallback chain:
1. Wiki memory → nếu có kết quả, trả về
2. Nếu Wiki trống → Web search → nếu có kết quả, trả về
3. Nếu cả hai thất bại → thông báo lỗi graceful
"""

import logging
from typing import Optional, List, Any

from src.config.settings import Config
from src.services.external.tavily_client import SearchResult

logger = logging.getLogger(__name__)


class SearchOrchestrator:
    """
    Điều phối tìm kiếm Wiki memory và Web search với fallback chain.

    Accepts wiki_storage (WikiStorage), embedding_service (LocalEmbeddingService),
    and tavily_client (TavilyClient) as dependencies. All are optional for graceful degradation.

    Example:
        orchestrator = SearchOrchestrator(
            wiki_storage=wiki_storage,
            embedding_service=embedding_service,
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
        wiki_storage: Optional[Any] = None,
        embedding_service: Optional[Any] = None,
        tavily_client: Optional[Any] = None,
    ):
        """
        Initialize SearchOrchestrator.

        Args:
            wiki_storage: WikiStorage instance for T2 Wiki Pages
            embedding_service: LocalEmbeddingService for query embedding
            tavily_client: TavilyClient for web search
        """
        self.wiki_storage = wiki_storage
        self.embedding_service = embedding_service
        self.tavily_client = tavily_client

        logger.info(
            f"SearchOrchestrator initialized - "
            f"wiki_storage={wiki_storage is not None}, "
            f"embedding_service={embedding_service is not None}, "
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
            mode: Search mode - "auto" (default), "wiki", or "web"
                - "auto": Wiki → Web → error (fallback chain)
                - "wiki": Wiki memory only
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
        elif mode == "wiki":
            return await self._search_wiki_only(user_id, query, **kwargs)
        elif mode == "web":
            return await self._search_web_only(query, **kwargs)
        else:
            return f"Lỗi: Mode '{mode}' không hợp lệ. Dùng: auto, wiki, hoặc web."

    async def _search_auto(self, user_id: str, query: str, **kwargs) -> str:
        """
        Fallback chain: Wiki → Web → error.

        1. Try Wiki memory (semantic search) — if results found, return
        2. If Wiki empty → try Tavily web search — if results found, return
        3. If both fail → graceful error message
        """
        # Step 1: Try Wiki memory
        logger.info("📚 SearchOrchestrator: Trying Wiki memory search...")
        wiki_results = await self._search_wiki(user_id, query)
        if wiki_results:
            logger.info(f"✅ SearchOrchestrator: Wiki returned {len(wiki_results)} results")
            return self._format_wiki_results(wiki_results, query)

        logger.info("📚 SearchOrchestrator: Wiki returned no results, trying Web search...")

        # Step 2: Try Web search
        web_result = await self._search_web(query, **kwargs)
        if web_result:
            logger.info("✅ SearchOrchestrator: Web search returned results")
            return self._format_web_result(web_result, query)

        # Step 3: Both failed
        logger.warning(f"⚠️ SearchOrchestrator: Both Wiki and Web search failed for '{query[:50]}'")
        return (
            f"Không tìm thấy thông tin nào về '{query}' trong ký ức hoặc trên web. "
            "Bạn thử hỏi với từ khóa khác nhé?"
        )

    async def _search_wiki_only(self, user_id: str, query: str, **kwargs) -> str:
        """Wiki memory search only."""
        logger.info("📚 SearchOrchestrator: Wiki-only search mode")
        wiki_results = await self._search_wiki(user_id, query)
        if wiki_results:
            return self._format_wiki_results(wiki_results, query)
        return f"Không tìm thấy ký ức nào liên quan đến '{query}'."

    async def _search_web_only(self, query: str, **kwargs) -> str:
        """Web search only."""
        logger.info("🌐 SearchOrchestrator: Web-only search mode")
        web_result = await self._search_web(query, **kwargs)
        if web_result:
            return self._format_web_result(web_result, query)
        return f"Không tìm thấy kết quả web nào cho '{query}'."

    async def _search_wiki(self, user_id: str, query: str) -> List[Any]:
        """
        Search Wiki memory using semantic search.

        Args:
            user_id: Discord user ID
            query: Search query string

        Returns:
            List of WikiPagePayload objects, empty if no results or service unavailable
        """
        if not self.wiki_storage:
            logger.warning("SearchOrchestrator: wiki_storage not available, skipping Wiki search")
            return []

        if not self.embedding_service:
            logger.warning(
                "SearchOrchestrator: embedding_service not available, skipping Wiki search"
            )
            return []

        try:
            query_vector = await self.embedding_service.get_embedding(query)
            if not query_vector:
                logger.warning("SearchOrchestrator: Failed to generate embedding for query")
                return []

            results = await self.wiki_storage.search_similar(
                user_id=user_id,
                query_vector=query_vector,
                top_k=Config.SEARCH_TOP_K_SEMANTIC,
                min_relevance=Config.SEARCH_MIN_RELEVANCE,
            )

            return results or []

        except Exception as e:
            logger.error(f"SearchOrchestrator: Wiki search error: {e}")
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
        wiki_results: List[Any],
        web_result: Optional[SearchResult],
    ) -> str:
        """
        Merge Wiki and Web results with Wiki first.

        This is the public API for combining results from both sources.
        Wiki results are listed first, followed Web search sources.

        Args:
            wiki_results: List of WikiPagePayload objects
            web_result: Optional SearchResult from Tavily

        Returns:
            str: Merged formatted results in Vietnamese
        """
        lines = []

        if wiki_results:
            lines.append("📚 **Kết quả từ Wiki Memory:**")
            lines.append(self._format_wiki_results(wiki_results, ""))
            lines.append("")

        if web_result and web_result.sources:
            lines.append("🌐 **Kết quả từ Web Search:**")
            lines.append(self._format_web_sources(web_result))

        return "\n".join(lines)

    def _format_wiki_results(self, results: List[Any], query: str) -> str:
        """Format Wiki results for LLM consumption."""
        lines = [f"Đã tìm thấy {len(results)} kết quả trong Wiki Memory cho '{query}':\n"]

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
            f"wiki_storage={self.wiki_storage is not None}, "
            f"embedding={self.embedding_service is not None}, "
            f"tavily={self.tavily_client is not None}>"
        )
