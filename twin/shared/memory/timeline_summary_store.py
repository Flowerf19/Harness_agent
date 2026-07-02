"""Timeline summary storage — T2 memory layer (schema v2).

Schema v2 changes vs v1:
- Field 'content' renamed to 'summary' (TEXT, BM25-indexed).
- Added fields: topic (TAG), topic_display (TEXT), version (NUMERIC).
- importance promoted to SORTABLE NUMERIC.
- embedding DIM driven by embedding_dim param (no more hardcoded 1024).
- Hybrid search: KNN + BM25 fused via RRF.
"""
from __future__ import annotations

import logging
import re
import struct
import uuid
from datetime import datetime, timezone
from typing import Any

from twin.shared.config.settings import Config

logger = logging.getLogger(__name__)


class TimelineSummary:
    """A timeline summary entry — one topic from one consolidation pass."""

    def __init__(
        self,
        user_id: str,
        summary: str,
        embedding: list[float],
        topic: str = "general",
        topic_display: str = "",
        importance: int = 3,
        version: int = 2,
        summary_id: str | None = None,
        created_at: datetime | None = None,
    ):
        self.summary_id = summary_id or str(uuid.uuid4())
        self.user_id = user_id
        self.summary = summary
        self.topic = topic
        self.topic_display = topic_display
        self.embedding = embedding
        self.importance = importance
        self.version = version
        self.created_at = created_at or datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary_id": self.summary_id,
            "user_id": self.user_id,
            "summary": self.summary,
            "topic": self.topic,
            "topic_display": self.topic_display,
            "embedding": self.embedding,
            "importance": self.importance,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
        }


class TimelineSummaryStore:
    """
    Vector + BM25 store for timeline summaries (T2).

    Search modes:
    - KNN only: search(user_id, query_embedding, limit)
    - Hybrid:   search(user_id, query_embedding, limit, query_text=..., topic_filter=...)
                Fuses KNN + BM25 results via RRF.
    """

    def __init__(self, redis_client: Any, embedding_dim: int = 384):
        self.redis = redis_client
        self.embedding_dim = embedding_dim
        self.index_name = "timeline_summaries"
        self.prefix = "timeline:summary"

    # ---------------------------------------------------------------- init

    async def initialize(self) -> None:
        """Create Redis index (schema v2) if not exists."""
        try:
            await self.redis.execute_command("FT.INFO", self.index_name)
            logger.info("Timeline index already exists")
        except Exception:
            await self.redis.execute_command(
                "FT.CREATE", self.index_name,
                "ON", "HASH",
                "PREFIX", "1", f"{self.prefix}:",
                "SCHEMA",
                "user_id",       "TAG",
                "topic",         "TAG",
                "topic_display", "TEXT",
                "summary",       "TEXT",
                "importance",    "NUMERIC", "SORTABLE",
                "created_at",    "NUMERIC", "SORTABLE",
                "version",       "NUMERIC",
                "embedding",     "VECTOR", "HNSW", "6",
                "TYPE", "FLOAT32",
                "DIM", str(self.embedding_dim),
                "DISTANCE_METRIC", "COSINE",
            )
            logger.info("Created timeline index (schema v2, dim=%d)", self.embedding_dim)

    # ---------------------------------------------------------------- write

    async def store_summary(
        self,
        user_id: str,
        summary: str,
        embedding: list[float],
        *,
        topic: str = "general",
        topic_display: str = "",
        importance: int = 3,
    ) -> str:
        """Store a topic summary; return summary_id."""
        if len(embedding) != self.embedding_dim:
            logger.warning(
                "store_summary: embedding dim mismatch — got %d, expected %d (user=%s)",
                len(embedding), self.embedding_dim, user_id,
            )

        entry = TimelineSummary(
            user_id=user_id,
            summary=summary,
            embedding=embedding,
            topic=topic,
            topic_display=topic_display,
            importance=importance,
        )

        key = f"{self.prefix}:{entry.summary_id}"
        await self.redis.hset(
            key,
            mapping={
                "user_id":       user_id,
                "summary":       summary,
                "topic":         topic,
                "topic_display": topic_display,
                "importance":    importance,
                "created_at":    entry.created_at.timestamp(),
                "version":       entry.version,
                "embedding":     self._pack_embedding(embedding),
            },
        )

        ttl_days = self._importance_to_ttl(importance)
        await self.redis.expire(key, ttl_days * 86400)

        logger.info(
            "Stored T2 summary %s topic=%s user=%s",
            entry.summary_id, topic, user_id,
        )
        return entry.summary_id

    # ---------------------------------------------------------------- search

    async def search(
        self,
        user_id: str,
        query_embedding: list[float],
        limit: int = 5,
        *,
        query_text: str | None = None,
        topic_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Hybrid (KNN + BM25 RRF) or pure KNN search.

        Args:
            user_id: filter by user.
            query_embedding: vector (should be prefixed with "query: " before calling get_embedding).
            limit: max results.
            query_text: if provided, also run BM25 and fuse via RRF.
            topic_filter: optional TAG filter (e.g. "work").
        """
        knn_results = await self._search_knn(user_id, query_embedding, limit, topic_filter)

        if not query_text:
            return knn_results

        bm25_results = await self._search_bm25(user_id, query_text, limit, topic_filter)
        return _rrf_fuse(knn_results, bm25_results, limit=limit)

    async def _search_knn(
        self,
        user_id: str,
        query_embedding: list[float],
        limit: int,
        topic_filter: str | None,
    ) -> list[dict[str, Any]]:
        """KNN semantic search."""
        tag_filter = f"@user_id:{{{user_id}}}"
        if topic_filter:
            tag_filter += f" @topic:{{{topic_filter}}}"
        query = f"({tag_filter})=>[KNN {limit} @embedding $vec AS score]"

        try:
            results = await self.redis.execute_command(
                "FT.SEARCH", self.index_name,
                query,
                "PARAMS", "2", "vec", self._pack_embedding(query_embedding),
                "SORTBY", "score", "ASC",
                "LIMIT", "0", str(limit),
                "DIALECT", "2",
            )
            return self._gate_by_similarity(self._parse_results(results))
        except Exception as exc:
            logger.error("Timeline KNN search failed: %s", exc)
            return []

    def _gate_by_similarity(
        self, results: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Drop KNN hits below the cosine-similarity floor.

        The index uses COSINE distance, so `score` = 1 - cosine_similarity.
        Without this gate a nearly-empty or off-topic T2 store still injects its
        top-K into every prompt (garbage-in → garbage-out). No-op when the floor
        is 0.0 (legacy) or a hit is missing its score.
        """
        min_cos = getattr(Config, "T2_MIN_COSINE", 0.0)
        if min_cos <= 0.0:
            return results
        kept: list[dict[str, Any]] = []
        for doc in results:
            dist = doc.get("score")
            if dist is None:
                kept.append(doc)
                continue
            similarity = 1.0 - float(dist)
            if similarity >= min_cos:
                kept.append(doc)
            else:
                logger.debug(
                    "T2 gate: drop summary_id=%s cosine=%.3f < %.2f",
                    doc.get("summary_id"), similarity, min_cos,
                )
        return kept

    async def _search_bm25(
        self,
        user_id: str,
        query_text: str,
        limit: int,
        topic_filter: str | None,
    ) -> list[dict[str, Any]]:
        """BM25 full-text search on the 'summary' field."""
        safe_text = re.sub(r"[^a-zA-Z0-9\sÀ-ɏẠ-ỹ]", " ", query_text).strip()
        if not safe_text:
            return []

        # OR the terms: lexical recall wants "any keyword matches" (e.g. catch
        # "Rei"/"AMD"), not "all words present". RediSearch ANDs space-separated
        # terms by default, which would make BM25 almost never fire on natural
        # queries — silently degrading hybrid back to KNN-only.
        terms = [t for t in safe_text.split() if t]
        if not terms:
            return []
        term_group = " | ".join(terms)

        tag_filter = f"@user_id:{{{user_id}}}"
        if topic_filter:
            tag_filter += f" @topic:{{{topic_filter}}}"

        bm25_query = f"({tag_filter}) ({term_group})"

        try:
            results = await self.redis.execute_command(
                "FT.SEARCH", self.index_name,
                bm25_query,
                "SCORER", "BM25",
                "WITHSCORES",
                "LIMIT", "0", str(limit),
                "DIALECT", "2",
            )
            return self._parse_results(results, has_scores=True)
        except Exception as exc:
            logger.error("Timeline BM25 search failed: %s", exc)
            return []

    # ---------------------------------------------------------------- get_recent

    async def get_recent(self, user_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """Get recent summaries sorted by created_at DESC."""
        query = f"@user_id:{{{user_id}}}"
        try:
            results = await self.redis.execute_command(
                "FT.SEARCH", self.index_name,
                query,
                "SORTBY", "created_at", "DESC",
                "LIMIT", "0", str(limit),
            )
            return self._parse_results(results)
        except Exception as exc:
            logger.error("Timeline get_recent failed: %s", exc)
            return []

    # ---------------------------------------------------------------- helpers

    def _parse_results(
        self,
        results: Any,
        *,
        has_scores: bool = False,
    ) -> list[dict[str, Any]]:
        """Parse raw FT.SEARCH results (both dict and list format, with/without scores)."""
        summaries: list[dict[str, Any]] = []

        if isinstance(results, dict):
            raw = results.get(b"results") or results.get("results") or []
            for item in raw:
                key = item.get(b"id") or item.get("id")
                extra = item.get(b"extra_attributes") or item.get("extra_attributes") or {}
                d = self._decode_fields(extra)
                if key:
                    key_str = key.decode() if isinstance(key, bytes) else key
                    d["summary_id"] = key_str.replace(f"{self.prefix}:", "")
                # backward compat: expose 'content' alias for old readers
                if "summary" in d and "content" not in d:
                    d["content"] = d["summary"]
                summaries.append(d)
            return summaries

        # List format: [count, key, [fields...], key, [fields...], ...]
        # With scores: [count, key, score, [fields...], ...]
        i = 1
        while i < len(results):
            key = results[i]
            i += 1

            score = None
            if has_scores and i < len(results) and not isinstance(results[i], list):
                try:
                    score = float(results[i])
                    i += 1
                except (TypeError, ValueError):
                    pass

            if i < len(results) and isinstance(results[i], list):
                fields = results[i]
                i += 1
            else:
                continue

            d: dict[str, Any] = self._decode_fields(fields)

            if key:
                key_str = key.decode() if isinstance(key, bytes) else key
                d["summary_id"] = key_str.replace(f"{self.prefix}:", "")

            if score is not None:
                d["_score"] = score

            # backward compat alias
            if "summary" in d and "content" not in d:
                d["content"] = d["summary"]

            summaries.append(d)

        return summaries

    def _decode_fields(self, mapping: Any) -> dict[str, Any]:
        """Decode Redis hash fields; unpack embedding bytes to list[float]."""
        result: dict[str, Any] = {}
        for k, v in mapping.items():
            field_name = k.decode() if isinstance(k, bytes) else k
            try:
                field_value: Any = v.decode() if isinstance(v, bytes) else v
            except (UnicodeDecodeError, AttributeError):
                field_value = v

            if field_name == "embedding":
                field_value = self._unpack_embedding(field_value)
            elif field_name == "score":
                try:
                    field_value = float(field_value)
                except (TypeError, ValueError):
                    pass
            elif field_name in {"importance", "version"}:
                try:
                    field_value = int(field_value)
                except (TypeError, ValueError):
                    pass
            elif field_name == "created_at":
                try:
                    field_value = float(field_value)
                except (TypeError, ValueError):
                    pass

            result[field_name] = field_value
        return result

    def _unpack_embedding(self, value: Any) -> list[float]:
        """Unpack FLOAT32 bytes to a Python list of floats."""
        if isinstance(value, list):
            return [float(x) for x in value]
        if not isinstance(value, (bytes, bytearray)):
            return []
        count = len(value) // 4
        return list(struct.unpack(f"{count}f", value[: count * 4]))

    def _pack_embedding(self, embedding: list[float]) -> bytes:
        return struct.pack(f"{len(embedding)}f", *embedding)

    @staticmethod
    def _importance_to_ttl(importance: int) -> int:
        return {5: 365, 4: 180, 3: 90, 2: 30, 1: 7}.get(importance, 90)


# -------------------------------------------------------------------- RRF

def _rrf_fuse(
    knn_results: list[dict[str, Any]],
    bm25_results: list[dict[str, Any]],
    *,
    k: int = 60,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Reciprocal Rank Fusion of two result lists.

    score(d) = sum(1 / (k + rank)) across lists that contain d.
    Dedup by summary_id; KNN dict wins on field conflict.
    """
    scores: dict[str, float] = {}
    docs: dict[str, dict[str, Any]] = {}

    for rank, doc in enumerate(knn_results, start=1):
        sid = doc.get("summary_id", "")
        if not sid:
            continue
        scores[sid] = scores.get(sid, 0.0) + 1.0 / (k + rank)
        docs.setdefault(sid, doc)

    for rank, doc in enumerate(bm25_results, start=1):
        sid = doc.get("summary_id", "")
        if not sid:
            continue
        scores[sid] = scores.get(sid, 0.0) + 1.0 / (k + rank)
        # merge: keep KNN dict as base, add any missing fields from BM25
        if sid not in docs:
            docs[sid] = doc
        else:
            for k2, v in doc.items():
                docs[sid].setdefault(k2, v)

    ranked = sorted(scores.keys(), key=lambda s: scores[s], reverse=True)
    return [docs[sid] for sid in ranked[:limit]]
