"""Redis Stack storage for T2 memory."""
from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any

import redis.asyncio as redis

from twin.shared.config.settings import Config
from twin.shared.memories.t2.models import (
    T2Chunk,
    T2Fact,
    T2Page,
    calculate_relevance,
    expires_at_for_importance,
    get_ttl_by_importance,
)

logger = logging.getLogger(__name__)


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _cosine(a: list[float] | None, b: list[float] | None) -> float:
    if not a or not b:
        return 0.0
    pairs = list(zip(a, b))
    dot = sum(x * y for x, y in pairs)
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if not norm_a or not norm_b:
        return 0.0
    return dot / (norm_a * norm_b)


class T2Store:
    PAGE_PREFIX = "t2:page"
    CHUNK_PREFIX = "t2:chunk"
    FACT_PREFIX = "t2:fact"
    TIMELINE_PREFIX = "t2:timeline"
    PAGE_INDEX = "idx:t2:page"
    CHUNK_INDEX = "idx:t2:chunk"
    FACT_INDEX = "idx:t2:fact"

    def __init__(
        self,
        redis_client: redis.Redis | None = None,
        *,
        redis_url: str | None = None,
        redis_password: str | None = None,
        redis_db: int = 0,
        vector_size: int | None = None,
    ):
        self.redis = redis_client or redis.from_url(
            redis_url or Config.REDIS_URL,
            password=redis_password if redis_password is not None else Config.REDIS_PASSWORD,
            db=redis_db,
            decode_responses=True,
        )
        self.vector_size = vector_size or Config.EMBEDDING_VECTOR_SIZE

    async def initialize(self) -> None:
        await self._create_index(self.PAGE_INDEX, "t2:page:")
        await self._create_index(self.CHUNK_INDEX, "t2:chunk:")
        await self._create_index(self.FACT_INDEX, "t2:fact:")

    async def _create_index(self, name: str, prefix: str) -> None:
        try:
            await self.redis.execute_command("FT.INFO", name)
            return
        except Exception:
            pass
        try:
            await self.redis.execute_command(
                "FT.CREATE",
                name,
                "ON",
                "JSON",
                "PREFIX",
                "1",
                prefix,
                "SCHEMA",
                "$.doc_type",
                "AS",
                "doc_type",
                "TAG",
                "$.user_id",
                "AS",
                "user_id",
                "TAG",
                "$.scope",
                "AS",
                "scope",
                "TAG",
                "$.topic_id",
                "AS",
                "topic_id",
                "TAG",
                "$.canonical_topic",
                "AS",
                "canonical_topic",
                "TEXT",
                "$.category",
                "AS",
                "category",
                "TAG",
                "$.entities[*]",
                "AS",
                "entities",
                "TAG",
                "$.resolution_status",
                "AS",
                "resolution_status",
                "TAG",
                "$.user_sentiment",
                "AS",
                "user_sentiment",
                "TAG",
                "$.importance",
                "AS",
                "importance",
                "NUMERIC",
                "$.confidence",
                "AS",
                "confidence",
                "NUMERIC",
                "$.event_date_ts",
                "AS",
                "event_date",
                "NUMERIC",
                "$.updated_at_ts",
                "AS",
                "updated_at",
                "NUMERIC",
                "$.expires_at_ts",
                "AS",
                "expires_at",
                "NUMERIC",
            )
        except Exception as e:
            logger.debug("T2Store: index creation skipped for %s: %s", name, e)

    async def close(self) -> None:
        await self.redis.close()

    def page_key(self, user_id: str, topic_id: str) -> str:
        return f"{self.PAGE_PREFIX}:{user_id}:{topic_id}"

    def chunk_key(self, user_id: str, topic_id: str, chunk_id: str) -> str:
        return f"{self.CHUNK_PREFIX}:{user_id}:{topic_id}:{chunk_id}"

    def fact_key(self, user_id: str, topic_id: str, fact_id: str) -> str:
        return f"{self.FACT_PREFIX}:{user_id}:{topic_id}:{fact_id}"

    def timeline_key(self, user_id: str, topic_id: str) -> str:
        return f"{self.TIMELINE_PREFIX}:{user_id}:{topic_id}"

    async def upsert_page(self, page: T2Page) -> bool:
        now = datetime.now(timezone.utc)
        page.updated_at = page.updated_at or now
        page.ttl_days = page.ttl_days or get_ttl_by_importance(page.importance)
        page.expires_at = page.expires_at or expires_at_for_importance(page.importance, now)
        ttl_seconds = max(60, int((page.expires_at - now).total_seconds()))
        return await self._set_json(self.page_key(page.user_id, page.topic_id), page.model_dump(mode="json"), ttl_seconds)

    async def upsert_chunk(self, chunk: T2Chunk) -> bool:
        now = datetime.now(timezone.utc)
        chunk.expires_at = chunk.expires_at or expires_at_for_importance(chunk.importance, now)
        ttl_seconds = max(60, int((chunk.expires_at - now).total_seconds()))
        ok = await self._set_json(
            self.chunk_key(chunk.user_id, chunk.topic_id, chunk.chunk_id),
            chunk.model_dump(mode="json"),
            ttl_seconds,
        )
        await self.redis.zadd(self.timeline_key(chunk.user_id, chunk.topic_id), {chunk.chunk_id: chunk.event_date.timestamp()})
        await self.redis.expire(self.timeline_key(chunk.user_id, chunk.topic_id), ttl_seconds)
        return ok

    async def upsert_fact(self, fact: T2Fact) -> bool:
        now = datetime.now(timezone.utc)
        fact.expires_at = fact.expires_at or expires_at_for_importance(fact.importance, now)
        ttl_seconds = max(60, int((fact.expires_at - now).total_seconds()))
        return await self._set_json(self.fact_key(fact.user_id, fact.topic_id, fact.fact_id), fact.model_dump(mode="json"), ttl_seconds)

    async def _set_json(self, key: str, data: dict[str, Any], ttl_seconds: int) -> bool:
        payload = json.dumps(self._with_index_fields(data), ensure_ascii=False, default=_json_default)
        try:
            await self.redis.execute_command("JSON.SET", key, "$", payload)
        except Exception:
            await self.redis.set(key, payload)
        await self.redis.expire(key, ttl_seconds)
        return True

    def _with_index_fields(self, data: dict[str, Any]) -> dict[str, Any]:
        data = dict(data)
        data.setdefault("doc_type", "page" if "page_id" in data else "chunk" if "chunk_id" in data else "fact")
        for field in ("event_date", "created_at", "updated_at", "last_accessed", "expires_at"):
            if data.get(field):
                dt = datetime.fromisoformat(data[field]) if isinstance(data[field], str) else data[field]
                data[f"{field}_ts"] = dt.timestamp()
        return data

    async def _get_json(self, key: str) -> dict[str, Any] | None:
        raw = None
        try:
            raw = await self.redis.execute_command("JSON.GET", key)
        except Exception:
            raw = await self.redis.get(key)
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode()
        return json.loads(raw)

    async def lookup_page(self, user_id: str, topic_id: str) -> T2Page | None:
        data = await self._get_json(self.page_key(user_id, topic_id))
        return T2Page.model_validate(data) if data else None

    async def lookup_by_page_id(self, page_id: str) -> T2Page | None:
        for page in await self.list_pages(limit=1000):
            if page.page_id == page_id:
                return page
        return None

    async def lookup_chunk(self, user_id: str, topic_id: str, chunk_id: str) -> T2Chunk | None:
        data = await self._get_json(self.chunk_key(user_id, topic_id, chunk_id))
        return T2Chunk.model_validate(data) if data else None

    async def list_pages(self, user_id: str | None = None, limit: int = 100) -> list[T2Page]:
        pages = []
        pattern = f"{self.PAGE_PREFIX}:{user_id}:*" if user_id else f"{self.PAGE_PREFIX}:*"
        async for key in self.redis.scan_iter(pattern, count=limit):
            data = await self._get_json(key)
            if data:
                pages.append(T2Page.model_validate(data))
            if len(pages) >= limit:
                break
        return pages

    async def list_all_for_user(self, user_id: str, limit: int = 100) -> list[T2Page]:
        return await self.list_pages(user_id=user_id, limit=limit)

    async def list_chunks(
        self,
        user_id: str,
        topic_id: str | None = None,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 50,
    ) -> list[T2Chunk]:
        chunks = []
        pattern = f"{self.CHUNK_PREFIX}:{user_id}:{topic_id}:*" if topic_id else f"{self.CHUNK_PREFIX}:{user_id}:*"
        async for key in self.redis.scan_iter(pattern, count=limit):
            data = await self._get_json(key)
            if not data:
                continue
            chunk = T2Chunk.model_validate(data)
            if start and chunk.event_date < start:
                continue
            if end and chunk.event_date > end:
                continue
            chunks.append(chunk)
            if len(chunks) >= limit:
                break
        chunks.sort(key=lambda c: c.event_date, reverse=True)
        return chunks

    async def search_similar(
        self,
        user_id: str,
        query_vector: list[float],
        top_k: int = 5,
        min_relevance: float = 0.5,
    ) -> list[T2Page]:
        now = datetime.now(timezone.utc)
        scored = []
        for page in await self.list_pages(user_id=user_id, limit=500):
            if page.expires_at and page.expires_at <= now:
                continue
            vector_score = max(
                _cosine(page.summary_embedding, query_vector),
                _cosine(page.latest_chunk_embedding, query_vector),
            )
            relevance = calculate_relevance(page, now)
            score = vector_score * relevance
            if score >= min_relevance:
                scored.append((score, page))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [page for _, page in scored[:top_k]]

    async def search_by_time(self, user_id: str, days: int = 7, top_k: int = 10) -> list[T2Chunk]:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        return await self.list_chunks(user_id, start=start, end=end, limit=top_k)

    async def search_by_topic(self, user_id: str, topic_keyword: str, top_k: int = 10) -> list[T2Page]:
        keyword = topic_keyword.lower()
        pages = [
            page for page in await self.list_pages(user_id=user_id, limit=500)
            if keyword in page.canonical_topic.lower()
            or any(keyword in alias.lower() for alias in page.topic_aliases)
            or any(keyword in entity.lower() for entity in page.entities)
        ]
        pages.sort(key=lambda p: (p.importance, p.updated_at), reverse=True)
        return pages[:top_k]

    async def recent(self, user_id: str, limit: int = 5) -> list[T2Page]:
        pages = await self.list_pages(user_id=user_id, limit=500)
        pages.sort(key=lambda p: p.updated_at, reverse=True)
        return pages[:limit]

    async def refresh_access(self, page_id: str) -> None:
        page = await self.lookup_by_page_id(page_id)
        if not page:
            return
        page.last_accessed = datetime.now(timezone.utc)
        page.access_count += 1
        page.expires_at = expires_at_for_importance(page.importance, page.last_accessed)
        await self.upsert_page(page)

    async def refresh_pages(self, pages: list[T2Page]) -> None:
        for page in pages:
            await self.refresh_access(page.page_id)

    async def delete_page(self, page_id: str) -> bool:
        page = await self.lookup_by_page_id(page_id)
        if not page:
            return False
        await self.redis.delete(self.page_key(page.user_id, page.topic_id))
        return True
