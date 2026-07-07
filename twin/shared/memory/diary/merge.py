"""Same-day diary merge for T2 timeline summaries (write-path P2.2).

Merges a new summary into an existing same-user+same-day doc when
cosine similarity clears T2_MERGE_MIN_COSINE, instead of always
appending. Takes the store duck-typed (not TimelineSummaryStore) to
avoid a circular import with store.py.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from twin.shared.config.settings import Config
from twin.shared.memory.diary.codec import (
    escape_tag_value,
    importance_to_ttl,
    pack_embedding,
    parse_results,
)

logger = logging.getLogger(__name__)


async def try_diary_merge(
    store: Any,
    *,
    user_id: str,
    day: str,
    summary: str,
    embedding: list[float],
    importance: int,
    period_start: float,
    period_end: float,
    source_entry_ids: list[str],
) -> str | None:
    """Merge `summary` into the best same-user same-day doc if similar
    enough; return the kept summary_id, or None to append instead.
    Best-effort: any lookup/re-embed hiccup falls back to append rather
    than risk corrupting an existing doc.
    """
    candidate = await find_diary_merge_candidate(store, user_id, day, embedding)
    if not candidate or not candidate.get("summary_id"):
        return None

    dist = candidate.get("score")
    if dist is None:
        return None
    similarity = 1.0 - float(dist)
    min_cos = float(getattr(Config, "T2_MERGE_MIN_COSINE", 0.60))
    if similarity < min_cos:
        return None

    old_summary = str(candidate.get("summary") or "")
    merged_text = f"{old_summary}\n{summary}" if old_summary else summary
    max_chars = int(getattr(Config, "T2_MERGE_MAX_CHARS", 1500))
    if len(merged_text) > max_chars:
        logger.info(
            "Diary merge skipped (would exceed %d chars) — appending new doc "
            "(user=%s day=%s target=%s)",
            max_chars, user_id, day, candidate["summary_id"],
        )
        return None

    try:
        merged_embedding = await store.embedding_service.get_embedding(
            f"{Config.EMBEDDING_PASSAGE_PREFIX}{merged_text}"
        )
    except Exception as exc:
        logger.warning("Diary merge re-embed failed — appending instead: %s", exc)
        return None
    if not merged_embedding or len(merged_embedding) != store.embedding_dim:
        logger.warning(
            "Diary merge re-embed returned dim=%s (expected %d) — appending instead",
            len(merged_embedding or []), store.embedding_dim,
        )
        return None

    old_importance = int(candidate.get("importance") or 3)
    new_importance = max(int(importance), old_importance)
    old_ps = candidate.get("period_start")
    old_pe = candidate.get("period_end")
    merged_ps = min(float(old_ps), period_start) if old_ps is not None else period_start
    merged_pe = max(float(old_pe), period_end) if old_pe is not None else period_end
    old_ids = candidate.get("source_entry_ids")
    if not isinstance(old_ids, list):
        old_ids = []
    # Order-preserving union: old provenance first, then the new batch.
    merged_ids = list(dict.fromkeys([*map(str, old_ids), *source_entry_ids]))

    summary_id = str(candidate["summary_id"])
    key = f"{store.prefix}:{summary_id}"
    await store.redis.hset(
        key,
        mapping={
            "summary":       merged_text,
            "importance":    new_importance,
            "period_start":  merged_ps,
            "period_end":    merged_pe,
            "source_entry_ids": json.dumps(merged_ids, ensure_ascii=False),
            "embedding":     pack_embedding(merged_embedding),
        },
    )
    await store.redis.expire(key, importance_to_ttl(new_importance) * 86400)

    logger.info(
        "Merged T2 diary summary %s user=%s day=%s cosine=%.3f chars=%d",
        summary_id, user_id, day, similarity, len(merged_text),
    )
    return summary_id


async def find_diary_merge_candidate(
    store: Any, user_id: str, day: str, embedding: list[float],
) -> dict[str, Any] | None:
    """Nearest same-user same-day doc (KNN 1), or None. The @day TAG
    filter is what enforces "never merge across days" — docs from other
    days (and old v2 docs, which have no day field at all) can't match.
    """
    query = (
        f"(@user_id:{{{escape_tag_value(user_id)}}} @day:{{{escape_tag_value(day)}}})"
        f"=>[KNN 1 @embedding $vec AS score]"
    )
    try:
        results = await store.redis.execute_command(
            "FT.SEARCH", store.index_name,
            query,
            "PARAMS", "2", "vec", pack_embedding(embedding),
            "SORTBY", "score", "ASC",
            "LIMIT", "0", "1",
            "DIALECT", "2",
        )
        parsed = parse_results(results, store.prefix)
        return parsed[0] if parsed else None
    except Exception as exc:
        logger.warning("Diary merge lookup failed — appending instead: %s", exc)
        return None
