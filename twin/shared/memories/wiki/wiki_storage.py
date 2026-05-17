"""Compatibility wrapper for Redis-backed T2 storage."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Optional

from twin.shared.memories.t2.store import T2Store
from twin.shared.memories.wiki.models.wiki_page import WikiPagePayload, calculate_relevance


class WikiStorage(T2Store):
    """Backward-compatible name for the Redis Stack T2Store.

    Existing tests and callers still import ``WikiStorage``/``WikiPagePayload``.
    New runtime code should use ``T2Store`` and ``T2Page`` directly.
    """

    COLLECTION_NAME = "t2_pages"

    def __init__(self, url: str | None = None, api_key: Optional[str] = None, vector_size: int | None = None, **kwargs):
        self.url = url
        self.api_key = api_key
        self._client = None
        super().__init__(vector_size=vector_size, **kwargs)

    async def initialize(self) -> None:
        if self._client is not None:
            collections = await self._client.get_collections()
            existing = [c.name for c in collections.collections]
            if self.COLLECTION_NAME not in existing:
                await self._client.create_collection(self.COLLECTION_NAME)
            return
        await super().initialize()

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            return
        await super().close()

    async def lookup_by_page_id(self, page_id: str):
        if self._client is not None:
            results, _ = await self._client.scroll(
                collection_name=self.COLLECTION_NAME,
                scroll_filter=SimpleNamespace(
                    must=[SimpleNamespace(key="page_id", match=SimpleNamespace(value=page_id))]
                ),
                limit=1,
                with_payload=True,
                with_vectors=True,
            )
            return self._point_to_page(results[0]) if results else None
        return await super().lookup_by_page_id(page_id)

    async def upsert_page(self, page) -> bool:
        if self._client is not None:
            if not page.embedding:
                return False
            point = SimpleNamespace(id=page.page_id, vector=page.embedding, payload=page.model_dump(mode="json"))
            await self._client.upsert(self.COLLECTION_NAME, points=[point])
            return True
        return await super().upsert_page(self._wiki_to_t2(page))

    async def list_all_for_user(self, user_id: str, limit: int = 100):
        if self._client is not None:
            results, _ = await self._client.scroll(
                collection_name=self.COLLECTION_NAME,
                scroll_filter=SimpleNamespace(
                    must=[SimpleNamespace(key="user_id", match=SimpleNamespace(value=user_id))]
                ),
                limit=limit,
                with_payload=True,
                with_vectors=True,
            )
            return [self._point_to_page(point) for point in results if self._point_to_page(point)]
        return [self._t2_to_wiki(page) for page in await super().list_all_for_user(user_id, limit)]

    async def search_similar(self, user_id: str, query_vector: list[float], top_k: int = 5, min_relevance: float = 0.5):
        if self._client is not None:
            results = await self._client.query_points(
                collection_name=self.COLLECTION_NAME,
                query=query_vector,
                query_filter=SimpleNamespace(
                    must=[SimpleNamespace(key="user_id", match=SimpleNamespace(value=user_id))]
                ),
                limit=top_k * 2,
                with_payload=True,
                with_vectors=True,
            )
            now = datetime.now(timezone.utc)
            pages = []
            for point in results.points:
                page = self._point_to_page(point)
                if page and calculate_relevance(page, now) >= min_relevance:
                    pages.append(page)
            return pages[:top_k]
        return [self._t2_to_wiki(page) for page in await super().search_similar(user_id, query_vector, top_k, min_relevance)]

    async def search_by_time(self, user_id: str, days: int = 7, top_k: int = 10):
        pages = await self.list_all_for_user(user_id, limit=500)
        now = datetime.now(timezone.utc)
        filtered = [page for page in pages if (now - page.last_updated).days <= days]
        filtered.sort(key=lambda p: p.last_updated, reverse=True)
        return filtered[:top_k]

    async def search_by_topic(self, user_id: str, topic_keyword: str, top_k: int = 10):
        pages = await self.list_all_for_user(user_id, limit=500)
        keyword = topic_keyword.lower()
        filtered = [page for page in pages if keyword in page.canonical_topic.lower()]
        filtered.sort(key=lambda p: p.importance, reverse=True)
        return filtered[:top_k]

    async def refresh_access(self, page_id: str) -> None:
        page = await self.lookup_by_page_id(page_id)
        if not page:
            return
        page.last_accessed = datetime.now(timezone.utc)
        page.access_count += 1
        await self.upsert_page(page)

    async def delete_page(self, page_id: str) -> bool:
        if self._client is not None:
            await self._client.delete(self.COLLECTION_NAME, points_selector=SimpleNamespace(points=[page_id]))
            return True
        return await super().delete_page(page_id)

    def _point_to_page(self, point) -> Optional[WikiPagePayload]:
        try:
            payload = point.payload
            vector = getattr(point, "vector", None)
            payload = dict(payload)
            for field in ("created_at", "last_updated", "last_accessed"):
                if isinstance(payload.get(field), str):
                    payload[field] = datetime.fromisoformat(payload[field])
            payload["embedding"] = vector
            return WikiPagePayload.model_validate(payload)
        except Exception:
            return None

    def _wiki_to_t2(self, page):
        from twin.shared.memories.t2.models import T2Page

        return T2Page(
            page_id=page.page_id,
            user_id=page.user_id,
            topic_id=page.page_id,
            canonical_topic=page.canonical_topic,
            category=page.category,
            current_summary=page.current_summary,
            key_points=page.key_points,
            importance=page.importance,
            ttl_days=page.ttl_days,
            created_at=page.created_at,
            updated_at=page.last_updated,
            last_accessed=page.last_accessed,
            access_count=page.access_count,
            history_log=page.history_log,
            confidence=page.confidence,
            summary_embedding=page.embedding,
        )

    def _t2_to_wiki(self, page):
        return WikiPagePayload(
            page_id=page.page_id,
            user_id=page.user_id,
            canonical_topic=page.canonical_topic,
            category=page.category,
            current_summary=page.current_summary,
            key_points=page.key_points,
            importance=page.importance,
            ttl_days=page.ttl_days,
            created_at=page.created_at,
            last_updated=page.updated_at,
            last_accessed=page.last_accessed,
            access_count=page.access_count,
            history_log=page.history_log,
            confidence=page.confidence,
            embedding=page.summary_embedding,
        )
