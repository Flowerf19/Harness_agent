"""Facade for Redis-backed T2 memory."""
from __future__ import annotations

from typing import Any

from twin.shared.config.settings import Config
from twin.shared.memories.t2.embedder import T2Embedder
from twin.shared.memories.t2.models import T2Chunk, T2Fact, T2Page
from twin.shared.memories.t2.search import T2Search
from twin.shared.memories.t2.store import T2Store


class T2Memory:
    def __init__(self, store: T2Store, embedding_service: Any):
        self.storage = store
        self.store = store
        self.embedder = T2Embedder(embedding_service)
        self.search_service = T2Search(store, self.embedder)

    async def search_pages(
        self,
        user_id: str,
        query: str,
        top_k: int = 5,
        min_relevance: float = 0.5,
    ) -> list[T2Page]:
        query_vector = await self.embedder.embed_text(query)
        if not query_vector:
            return []
        pages = await self.store.search_similar(user_id, query_vector, top_k, min_relevance)
        await self.store.refresh_pages(pages)
        return pages

    async def search(
        self,
        user_id: str,
        mode: str = "auto",
        query: str | None = None,
        days: int | None = 7,
        topic: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 5,
        context_depth: int = 1,
        max_related_chunks: int = 5,
    ) -> str:
        return await self.search_service.search(
            user_id,
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

    async def embed_page(self, page: Any, latest_chunk: T2Chunk | None = None, facts: list[T2Fact] | None = None) -> bool:
        page = self._coerce_page(page)
        await self.embedder.embed_page(page, facts=facts, latest_chunk=latest_chunk)
        return await self.store.upsert_page(page)

    async def upsert_page_with_chunk(
        self,
        page: T2Page,
        chunk: T2Chunk,
        facts: list[T2Fact] | None = None,
    ) -> bool:
        await self.embedder.embed_page(page, facts=facts, latest_chunk=chunk)
        if chunk.content:
            chunk.embedding = await self.embedder.embed_text(chunk.content)
        for fact in facts or []:
            await self.store.upsert_fact(fact)
        await self.store.upsert_chunk(chunk)
        return await self.store.upsert_page(page)

    async def lookup_by_page_id(self, page_id: str):
        return await self.store.lookup_by_page_id(page_id)

    async def refresh_access(self, page_id: str) -> None:
        await self.store.refresh_access(page_id)

    async def clear_embedding_cache(self):
        service = getattr(self.embedder.embedding_service, "_cache", None)
        if service is not None:
            service.clear()

    def _coerce_page(self, page: Any) -> T2Page:
        if isinstance(page, T2Page):
            return page
        topic_id = getattr(page, "page_id", None) or getattr(page, "topic_id", None)
        return T2Page(
            page_id=getattr(page, "page_id"),
            user_id=getattr(page, "user_id"),
            topic_id=topic_id,
            canonical_topic=getattr(page, "canonical_topic"),
            category=getattr(page, "category", "casual"),
            current_summary=getattr(page, "current_summary", ""),
            key_points=getattr(page, "key_points", []),
            importance=getattr(page, "importance", 3),
            ttl_days=getattr(page, "ttl_days", 30),
            created_at=getattr(page, "created_at"),
            updated_at=getattr(page, "last_updated", getattr(page, "updated_at")),
            last_accessed=getattr(page, "last_accessed"),
            access_count=getattr(page, "access_count", 0),
            history_log=getattr(page, "history_log", []),
            confidence=getattr(page, "confidence", 1.0),
            summary_embedding=getattr(page, "embedding", None),
        )
