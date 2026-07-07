"""Timeline summary storage — T2 memory layer (schema v3: diary model).

TimelineSummaryStore orchestrates write (store_summary, same-day diary
merge) and hybrid KNN+BM25 search over Redis Stack. Field encode/decode
lives in codec.py, same-day merge in merge.py, and index
DDL/introspection in schema.py.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from twin.shared.config.settings import Config
from twin.shared.llm.embedding.embedding_trace_logger import cosine_similarity
from twin.shared.memory.diary.merge import try_diary_merge
from twin.shared.memory.diary.codec import (
    escape_tag_value,
    importance_to_ttl,
    pack_embedding,
    parse_results,
)
from twin.shared.memory.diary.schema import (
    create_timeline_index,
    ensure_diary_fields,
    extract_indexed_dim,
)
from twin.shared.memory.vn_time import vn_day_str

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
    """Vector + BM25 store for timeline summaries (T2).

    search() supports KNN-only or hybrid (KNN + BM25 fused via RRF)
    depending on whether query_text is passed.
    """

    def __init__(
        self,
        redis_client: Any,
        embedding_dim: int = 384,
        embedding_service: Any = None,
    ):
        self.redis = redis_client
        self.embedding_dim = embedding_dim
        # Only needed to re-embed merged text on a diary-merge write (P2.2).
        # None disables merging entirely (falls back to pre-diary
        # append-only behavior) — keeps every caller/test that constructs
        # this store without one working unchanged.
        self.embedding_service = embedding_service
        self.index_name = "timeline_summaries"
        self.prefix = "timeline:summary"

    # ---------------------------------------------------------------- init

    async def initialize(self) -> None:
        """Create Redis index (schema v3) if not exists."""
        try:
            info = await self.redis.execute_command("FT.INFO", self.index_name)
            logger.info("Timeline index already exists")
            indexed_dim = extract_indexed_dim(info)
            if indexed_dim is not None and indexed_dim != self.embedding_dim:
                logger.error(
                    "Timeline index %r is indexed with DIM=%d but the configured "
                    "embedding_dim=%d — writes/searches will silently fail to index "
                    "or will target the wrong vector space. A reindex is required "
                    "(this will NOT auto-drop the index).",
                    self.index_name, indexed_dim, self.embedding_dim,
                )
            await ensure_diary_fields(self.redis, self.index_name, info)
        except Exception:
            await create_timeline_index(
                self.redis, self.index_name, self.prefix, self.embedding_dim,
            )

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
        period_start: float | None = None,
        period_end: float | None = None,
        source_entry_ids: list[str] | None = None,
    ) -> str:
        """Store a topic summary as a diary entry; return summary_id.

        Same-day near-duplicates (cosine >= T2_MERGE_MIN_COSINE) merge into
        the existing doc instead of appending (needs embedding_service).
        Raises ValueError on embedding dim mismatch — storing anyway used to
        silently fail RediSearch indexing, leaving the summary unsearchable.
        """
        if len(embedding) != self.embedding_dim:
            raise ValueError(
                f"store_summary: embedding dim mismatch — got {len(embedding)}, "
                f"expected {self.embedding_dim} (user={user_id})"
            )

        now_ts = datetime.now(timezone.utc).timestamp()
        ps = float(period_start) if period_start is not None else now_ts
        pe = float(period_end) if period_end is not None else ps
        day = vn_day_str(ps)
        entry_ids = [str(x) for x in (source_entry_ids or [])]

        if self.embedding_service is not None:
            merged_id = await try_diary_merge(
                self,
                user_id=user_id,
                day=day,
                summary=summary,
                embedding=embedding,
                importance=importance,
                period_start=ps,
                period_end=pe,
                source_entry_ids=entry_ids,
            )
            if merged_id is not None:
                return merged_id

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
                "day":           day,
                "period_start":  ps,
                "period_end":    pe,
                "source_entry_ids": json.dumps(entry_ids, ensure_ascii=False),
                "embedding":     pack_embedding(embedding),
            },
        )

        ttl_days = importance_to_ttl(importance)
        await self.redis.expire(key, ttl_days * 86400)

        logger.info(
            "Stored T2 summary %s topic=%s user=%s day=%s",
            entry.summary_id, topic, user_id, day,
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
        since_ts: float | None = None,
        until_ts: float | None = None,
    ) -> list[dict[str, Any]]:
        """Hybrid (KNN + BM25 RRF) or pure KNN search, filtered by user_id
        and optional topic/time bounds. query_embedding is caller-composed
        (query prefix + text); pass query_text to also run BM25 fused via
        RRF.
        """
        # Built conditionally (not passed as since_ts=None, until_ts=None)
        # so unit tests that monkeypatch _search_knn/_search_bm25 with the
        # pre-P3.2 4-positional-arg signature keep working unfiltered.
        time_kwargs: dict[str, float] = {}
        if since_ts is not None:
            time_kwargs["since_ts"] = since_ts
        if until_ts is not None:
            time_kwargs["until_ts"] = until_ts

        knn_results = await self._search_knn(
            user_id, query_embedding, limit, topic_filter, **time_kwargs,
        )

        if not query_text:
            return self._gate_by_similarity(knn_results)

        bm25_results = await self._search_bm25(
            user_id, query_text, limit, topic_filter, **time_kwargs,
        )

        # Fuse WITHOUT truncation, then gate, THEN apply the final limit. If we
        # truncated to `limit` first, a gated doc ranked inside the fused top-N
        # would consume a slot and then get stripped, so a valid doc ranked just
        # below it is lost — under-returning even when enough valid docs exist.
        fused = _rrf_fuse(
            knn_results, bm25_results, limit=len(knn_results) + len(bm25_results),
        )

        # A doc the cosine gate would drop from KNN must not re-enter through
        # BM25's ungated results. Compute the ids the gate rejects from the raw
        # KNN hits and strip them from the fused output; BM25-only docs (never
        # seen by KNN, so not in gated_ids) pass through untouched.
        kept_ids = {d.get("summary_id") for d in self._gate_by_similarity(knn_results)}
        gated_ids = {d.get("summary_id") for d in knn_results} - kept_ids
        fused = [d for d in fused if d.get("summary_id") not in gated_ids]

        # P3.5 (fix B3): a doc KNN never scored (BM25-only) has no cosine
        # distance to gate on above, so it always passed fusion ungated —
        # turning BM25 into a bypass of T2_MIN_COSINE. Compute its cosine in
        # Python (its `embedding` field is present — no RETURN clause narrows
        # BM25's fields) and apply the SAME floor, so BM25 is ranking-only.
        fused = self._gate_bm25_only_by_cosine(fused, knn_results, query_embedding)

        return fused[:limit]

    @staticmethod
    def _time_filter_clause(since_ts: float | None, until_ts: float | None) -> str | None:
        """Build the RediSearch OR-fallback time filter clause (P3.2).

        RediSearch has no COALESCE: a doc missing `period_end` (pre-v3) never
        matches any range query on it, so `-@period_end:[-inf +inf]` isolates
        those docs and re-tests them against `created_at` instead. None when
        both bounds are unset.
        """
        if since_ts is None and until_ts is None:
            return None
        lo = since_ts if since_ts is not None else "-inf"
        hi = until_ts if until_ts is not None else "+inf"
        rng = f"[{lo} {hi}]"
        return f"(@period_end:{rng} | (-@period_end:[-inf +inf] @created_at:{rng}))"

    def _gate_bm25_only_by_cosine(
        self,
        fused: list[dict[str, Any]],
        knn_results: list[dict[str, Any]],
        query_embedding: list[float],
    ) -> list[dict[str, Any]]:
        """Apply the T2_MIN_COSINE floor to BM25-only docs (P3.5, fix B3).

        No-op when the floor is 0.0. Docs already seen by KNN were gated
        above; only docs reachable solely through BM25 are scored here. A
        doc missing an embedding is kept (fail-open), not dropped.
        """
        min_cos = getattr(Config, "T2_MIN_COSINE", 0.0)
        if min_cos <= 0.0:
            return fused
        knn_ids = {d.get("summary_id") for d in knn_results}
        kept: list[dict[str, Any]] = []
        for doc in fused:
            sid = doc.get("summary_id")
            if sid in knn_ids:
                kept.append(doc)
                continue
            embedding = doc.get("embedding")
            if not embedding or not query_embedding:
                kept.append(doc)
                continue
            try:
                similarity = cosine_similarity(query_embedding, embedding)
            except ValueError:
                kept.append(doc)
                continue
            if similarity >= min_cos:
                kept.append(doc)
            else:
                logger.debug(
                    "T2 gate (BM25-only): drop summary_id=%s cosine=%.3f < %.2f",
                    sid, similarity, min_cos,
                )
        return kept

    async def _search_knn(
        self,
        user_id: str,
        query_embedding: list[float],
        limit: int,
        topic_filter: str | None,
        *,
        since_ts: float | None = None,
        until_ts: float | None = None,
    ) -> list[dict[str, Any]]:
        """KNN semantic search. Returns raw hits ungated — callers apply the
        cosine gate (search() gates directly for pure-KNN, or post-fusion for
        hybrid so BM25 can't smuggle a gated-out doc back in)."""
        uid = escape_tag_value(user_id)
        tag_filter = f"@user_id:{{{uid}}}"
        if topic_filter:
            tag_filter += f" @topic:{{{escape_tag_value(topic_filter)}}}"
        time_clause = self._time_filter_clause(since_ts, until_ts)
        filter_expr = f"{tag_filter} {time_clause}" if time_clause else tag_filter
        query = f"({filter_expr})=>[KNN {limit} @embedding $vec AS score]"

        try:
            results = await self.redis.execute_command(
                "FT.SEARCH", self.index_name,
                query,
                "PARAMS", "2", "vec", pack_embedding(query_embedding),
                "SORTBY", "score", "ASC",
                "LIMIT", "0", str(limit),
                "DIALECT", "2",
            )
            return parse_results(results, self.prefix)
        except Exception as exc:
            logger.error("Timeline KNN search failed: %s", exc)
            return []

    def _gate_by_similarity(
        self, results: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Drop KNN hits below the cosine-similarity floor.

        score = 1 - cosine_similarity (COSINE index). Without this gate, a
        near-empty or off-topic T2 store still injects top-K noise into
        every prompt. No-op when the floor is 0.0 or a hit has no score.
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
        *,
        since_ts: float | None = None,
        until_ts: float | None = None,
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

        uid = escape_tag_value(user_id)
        tag_filter = f"@user_id:{{{uid}}}"
        if topic_filter:
            tag_filter += f" @topic:{{{escape_tag_value(topic_filter)}}}"
        time_clause = self._time_filter_clause(since_ts, until_ts)
        if time_clause:
            tag_filter += f" {time_clause}"

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
            return parse_results(results, self.prefix, has_scores=True)
        except Exception as exc:
            logger.error("Timeline BM25 search failed: %s", exc)
            return []

    # ---------------------------------------------------------------- get_recent

    async def get_recent(
        self,
        user_id: str,
        limit: int = 10,
        *,
        since_ts: float | None = None,
        until_ts: float | None = None,
    ) -> list[dict[str, Any]]:
        """Get recent summaries sorted by created_at DESC.

        since_ts/until_ts: optional epoch-second bounds on the diary period,
        same OR-fallback semantics as search() — see _time_filter_clause.
        """
        tag_filter = f"@user_id:{{{escape_tag_value(user_id)}}}"
        time_clause = self._time_filter_clause(since_ts, until_ts)
        query = f"({tag_filter} {time_clause})" if time_clause else tag_filter
        # DIALECT 2 only added when the OR/negation time_clause is actually in
        # play (same construct _search_knn/_search_bm25 already rely on
        # DIALECT 2 for) — the plain tag-only query keeps its exact prior args.
        dialect_args = ["DIALECT", "2"] if time_clause else []
        try:
            results = await self.redis.execute_command(
                "FT.SEARCH", self.index_name,
                query,
                "SORTBY", "created_at", "DESC",
                "LIMIT", "0", str(limit),
                *dialect_args,
            )
            return parse_results(results, self.prefix)
        except Exception as exc:
            logger.error("Timeline get_recent failed: %s", exc)
            return []


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
