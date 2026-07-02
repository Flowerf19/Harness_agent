"""Embedding trace logger — records embedding calls and similarity decisions.

Used for debugging embedding models and for downstream accuracy evaluation.
Writes JSON Lines (one JSON object per line) so eval scripts can read it with
``pandas.read_json(path, lines=True)`` or ``jq``.

The logger is intentionally synchronous and does its own file I/O; callers
invoke it from async code but the write is small and buffered. When disabled
(the default), it performs no I/O and has zero runtime overhead.
"""
from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class TraceRecord:
    """One embedding trace event.

    All fields are JSON-serializable primitives so the record can be dumped
    directly without custom encoders.
    """

    timestamp: str
    event_type: str
    model_name: str
    provider: str
    api_url: str
    vector_dim: int
    raw_dim: int | None
    l2_norm: float | None
    latency_ms: float
    cache_hit: bool
    input_text: str
    query_text: str | None = None
    matched_text: str | None = None
    cosine_similarity: float | None = None
    token_overlap: float | None = None
    action: str | None = None
    knn_score: float | None = None
    bm25_score: float | None = None
    rrf_rank: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two vectors. Returns 0.0 if either vector is zero."""
    if len(a) != len(b):
        raise ValueError(f"Vector dimension mismatch: {len(a)} vs {len(b)}")

    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


def token_overlap(a: str, b: str) -> float:
    """Jaccard-like overlap of token sets, matching semantic_trace.log semantics.

    Splits on whitespace, lowercases, and strips leading/trailing punctuation
    from each token. Returns 0.0 when either side is empty.
    """
    if not a or not b:
        return 0.0

    def _tokens(text: str) -> set[str]:
        return {
            "".join(ch for ch in token if ch.isalnum() or ch in {"_", "-"}).lower()
            for token in text.split()
            if token.strip()
        }

    set_a = _tokens(a)
    set_b = _tokens(b)
    if not set_a or not set_b:
        return 0.0

    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


class EmbeddingTraceLogger:
    """JSON Lines logger for embedding events.

    When ``enabled`` is False, all methods are no-ops and no file is created.
    """

    def __init__(self, log_path: str | os.PathLike[str], enabled: bool = False) -> None:
        self.enabled = enabled
        self.log_path = Path(log_path)
        if self.enabled:
            try:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                # Disable logging if the log directory cannot be created
                # (e.g. missing permissions inside a container). The service
                # should still start.
                self.enabled = False
                logging.getLogger(__name__).warning(
                    "Embedding trace log disabled: cannot create %s: %s",
                    self.log_path.parent,
                    exc,
                )

    def log(
        self,
        *,
        event_type: str,
        model_name: str,
        provider: str,
        api_url: str,
        vector_dim: int,
        raw_dim: int | None,
        l2_norm: float | None,
        latency_ms: float,
        cache_hit: bool,
        input_text: str,
        query_text: str | None = None,
        matched_text: str | None = None,
        cosine_similarity: float | None = None,
        token_overlap: float | None = None,
        action: str | None = None,
        knn_score: float | None = None,
        bm25_score: float | None = None,
        rrf_rank: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Append a trace record to the log file."""
        if not self.enabled:
            return

        record = TraceRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type=event_type,
            model_name=model_name,
            provider=provider,
            api_url=api_url,
            vector_dim=vector_dim,
            raw_dim=raw_dim,
            l2_norm=round(l2_norm, 6) if l2_norm is not None else None,
            latency_ms=round(latency_ms, 3),
            cache_hit=cache_hit,
            input_text=input_text,
            query_text=query_text,
            matched_text=matched_text,
            cosine_similarity=round(cosine_similarity, 6) if cosine_similarity is not None else None,
            token_overlap=round(token_overlap, 4) if token_overlap is not None else None,
            action=action,
            knn_score=round(knn_score, 6) if knn_score is not None else None,
            bm25_score=round(bm25_score, 6) if bm25_score is not None else None,
            rrf_rank=rrf_rank,
            extra=extra or {},
        )

        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
