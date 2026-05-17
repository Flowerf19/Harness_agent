"""Embedding text builders for T2 memory."""
from __future__ import annotations

from typing import Any

from twin.shared.memories.t2.models import T2Chunk, T2Fact, T2Page


class T2Embedder:
    def __init__(self, embedding_service: Any):
        self.embedding_service = embedding_service
        self._ready = False

    async def initialize(self) -> None:
        if not self._ready and hasattr(self.embedding_service, "initialize"):
            await self.embedding_service.initialize()
        self._ready = True

    def build_summary_text(self, page: T2Page, facts: list[T2Fact] | None = None) -> str:
        parts = [
            f"Topic: {page.canonical_topic}",
            f"Summary: {page.current_summary}",
            f"Category: {page.category}",
            f"Entities: {', '.join(page.entities)}",
            f"Status: {page.resolution_status}",
            f"Sentiment: {page.user_sentiment}",
        ]
        if page.key_points:
            parts.append("Key points: " + "; ".join(page.key_points))
        active_facts = [fact.claim for fact in facts or [] if fact.status == "active"]
        if active_facts:
            parts.append("Active facts: " + "; ".join(active_facts))
        return "\n".join(part for part in parts if part and not part.endswith(": "))

    def build_latest_chunk_text(self, page: T2Page, chunk: T2Chunk | None = None) -> str:
        if not chunk:
            return f"Topic: {page.canonical_topic}\nLatest: {page.current_summary}"
        return f"Topic: {page.canonical_topic}\nDate: {chunk.event_date.isoformat()}\nLatest: {chunk.content}"

    async def embed_text(self, text: str) -> list[float] | None:
        await self.initialize()
        return await self.embedding_service.get_embedding(text)

    async def embed_page(
        self,
        page: T2Page,
        *,
        facts: list[T2Fact] | None = None,
        latest_chunk: T2Chunk | None = None,
    ) -> T2Page:
        page.summary_embedding = await self.embed_text(self.build_summary_text(page, facts))
        page.latest_chunk_embedding = await self.embed_text(self.build_latest_chunk_text(page, latest_chunk))
        return page
