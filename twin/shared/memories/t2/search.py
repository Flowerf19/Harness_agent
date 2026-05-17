"""Search and formatting for T2 memory."""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any

from twin.shared.config.settings import Config
from twin.shared.memories.t2.models import T2Chunk, T2Page


class T2Search:
    def __init__(self, store: Any, embedder: Any):
        self.store = store
        self.embedder = embedder

    async def search(
        self,
        user_id: str,
        *,
        mode: str = "auto",
        query: str | None = None,
        days: int | None = None,
        topic: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 5,
        context_depth: int = 1,
        max_related_chunks: int = 5,
    ) -> str:
        concrete_mode = self._resolve_mode(mode, query=query, topic=topic, days=days, start_date=start_date, end_date=end_date)
        if concrete_mode == "semantic":
            return await self._semantic(user_id, query, limit)
        if concrete_mode == "time":
            return await self._time(user_id, query, days, start_date, end_date, limit)
        if concrete_mode == "topic":
            return await self._topic(user_id, topic or query, limit)
        if concrete_mode == "topic_timeline":
            return await self._topic_timeline(user_id, topic or query, start_date, end_date, limit)
        if concrete_mode == "related_context":
            return await self._related_context(user_id, topic or query, context_depth, max_related_chunks)
        if concrete_mode == "recent":
            return await self._recent(user_id, limit)
        return f"Lỗi: Mode '{mode}' không hợp lệ."

    def _resolve_mode(self, mode: str, **kwargs) -> str:
        if mode != "auto":
            return mode
        if kwargs.get("start_date") or kwargs.get("end_date") or kwargs.get("days"):
            return "time"
        if kwargs.get("topic"):
            return "topic"
        return "semantic" if kwargs.get("query") else "recent"

    async def _semantic(self, user_id: str, query: str | None, limit: int) -> str:
        if not query:
            return "Lỗi: Mode 'semantic' cần parameter 'query'."
        query_vector = await self.embedder.embed_text(query)
        if not query_vector:
            return "Lỗi: Không thể tạo embedding cho query."
        pages = await self.store.search_similar(
            user_id=user_id,
            query_vector=query_vector,
            top_k=limit,
            min_relevance=Config.SEARCH_MIN_RELEVANCE,
        )
        await self.store.refresh_pages(pages)
        return self._format_pages(pages, f"semantic: {query}")

    async def _time(
        self,
        user_id: str,
        query: str | None,
        days: int | None,
        start_date: str | None,
        end_date: str | None,
        limit: int,
    ) -> str:
        start, end, label = self._parse_range(days, start_date, end_date)
        chunks = await self.store.list_chunks(user_id, start=start, end=end, limit=limit * 3)
        if query and chunks:
            query_vector = await self.embedder.embed_text(query)
            chunks.sort(key=lambda c: self._chunk_score(c, query_vector), reverse=True)
        chunks = chunks[:limit]
        if not chunks:
            return f"Không tìm thấy ký ức nào trong khoảng {label}."
        return self._format_chunks(chunks, f"time: {label}")

    async def _topic(self, user_id: str, topic: str | None, limit: int) -> str:
        if not topic:
            return "Lỗi: Mode 'topic' cần parameter 'topic'."
        pages = await self.store.search_by_topic(user_id=user_id, topic_keyword=topic, top_k=limit)
        await self.store.refresh_pages(pages)
        if not pages:
            return f"Không tìm thấy ký ức nào với topic chứa '{topic}'."
        lines = [self._format_pages(pages, f"topic: {topic}")]
        for page in pages[:2]:
            chunks = await self.store.list_chunks(user_id, page.topic_id, limit=3)
            if chunks:
                lines.append(self._format_chunks(chunks, f"recent chunks: {page.canonical_topic}"))
        return "\n\n".join(lines)

    async def _topic_timeline(
        self,
        user_id: str,
        topic: str | None,
        start_date: str | None,
        end_date: str | None,
        limit: int,
    ) -> str:
        if not topic:
            return "Lỗi: Mode 'topic_timeline' cần parameter 'topic'."
        pages = await self.store.search_by_topic(user_id=user_id, topic_keyword=topic, top_k=1)
        if not pages:
            return f"Không tìm thấy topic '{topic}'."
        start, end, label = self._parse_range(None, start_date, end_date)
        chunks = await self.store.list_chunks(user_id, pages[0].topic_id, start=start, end=end, limit=limit)
        chunks.sort(key=lambda c: c.event_date)
        return self._format_chunks(chunks, f"timeline: {pages[0].canonical_topic} ({label})")

    async def _related_context(self, user_id: str, ref: str | None, depth: int, max_related_chunks: int) -> str:
        if not ref:
            return "Lỗi: Mode 'related_context' cần query hoặc topic."
        pages = await self.store.search_by_topic(user_id=user_id, topic_keyword=ref, top_k=1)
        if not pages:
            return f"Không tìm thấy related context cho '{ref}'."
        seen: set[str] = set()
        frontier = await self.store.list_chunks(user_id, pages[0].topic_id, limit=max_related_chunks)
        related: list[T2Chunk] = []
        for _ in range(max(depth, 0) + 1):
            next_frontier = []
            for chunk in frontier:
                if chunk.chunk_id in seen:
                    continue
                seen.add(chunk.chunk_id)
                related.append(chunk)
                for cid in [chunk.previous_chunk_id, chunk.next_chunk_id, *chunk.related_chunk_ids]:
                    if cid:
                        found = await self.store.lookup_chunk(user_id, chunk.topic_id, cid)
                        if found:
                            next_frontier.append(found)
                if len(related) >= max_related_chunks:
                    break
            frontier = next_frontier
            if len(related) >= max_related_chunks:
                break
        return self._format_chunks(related[:max_related_chunks], f"related_context: {ref}")

    async def _recent(self, user_id: str, limit: int) -> str:
        pages = await self.store.recent(user_id=user_id, limit=limit)
        await self.store.refresh_pages(pages)
        return self._format_pages(pages, "recent")

    def _parse_range(
        self,
        days: int | None,
        start_date: str | None,
        end_date: str | None,
    ) -> tuple[datetime, datetime, str]:
        now = datetime.now(timezone.utc)
        if start_date or end_date:
            start = datetime.combine(datetime.fromisoformat(start_date).date(), time.min, tzinfo=timezone.utc) if start_date else now - timedelta(days=3650)
            end = datetime.combine(datetime.fromisoformat(end_date).date(), time.max, tzinfo=timezone.utc) if end_date else now
            return start, end, f"{start.date()}..{end.date()}"
        lookback = days if days is not None else 7
        return now - timedelta(days=lookback), now, f"{lookback} ngày qua"

    def _chunk_score(self, chunk: T2Chunk, vector: list[float] | None) -> float:
        if not chunk.embedding or not vector:
            return chunk.event_date.timestamp()
        return sum(a * b for a, b in zip(chunk.embedding, vector))

    def _format_pages(self, pages: list[T2Page], context: str) -> str:
        if not pages:
            return f"Không tìm thấy ký ức nào ({context})."
        lines = [f"Đã tìm thấy {len(pages)} ký ức T2 ({context}):"]
        for i, page in enumerate(pages, 1):
            lines.append(f"\n{i}. **{page.canonical_topic}** (Category: {page.category})")
            lines.append(f"   Summary: {page.current_summary}")
            if page.key_points:
                lines.append("   Key Points:")
                for point in page.key_points[:5]:
                    lines.append(f"   - {point}")
            lines.append(f"   Updated: {page.updated_at.strftime('%Y-%m-%d %H:%M')}")
        return "\n".join(lines)

    def _format_chunks(self, chunks: list[T2Chunk], context: str) -> str:
        if not chunks:
            return f"Không tìm thấy chunk nào ({context})."
        lines = [f"Đã tìm thấy {len(chunks)} memory chunks ({context}):"]
        for i, chunk in enumerate(chunks, 1):
            lines.append(f"\n{i}. {chunk.event_date.strftime('%Y-%m-%d %H:%M')}")
            lines.append(f"   {chunk.content}")
        return "\n".join(lines)
