"""Abstract base for embedding services (OpenAI-compat, Gemini, ...)."""

from __future__ import annotations

import abc
import logging
import math
from typing import TYPE_CHECKING, Any, List

import aiohttp

if TYPE_CHECKING:
    from .embedding_trace_logger import EmbeddingTraceLogger


class BaseEmbeddingService(abc.ABC):
    """
    Common interface for all embedding providers.

    Subclasses implement `get_embedding(text)` against a specific provider's
    HTTP protocol. Shared concerns (aiohttp session, in-memory LRU cache,
    cleanup) live here so providers stay focused on payload shape.
    """

    def __init__(
        self,
        model_name: str,
        *,
        expected_dim: int | None = None,
        cache_size: int = 100,
        trace_logger: EmbeddingTraceLogger | None = None,
        provider: str = "unknown",
        api_url: str = "",
    ):
        self.model_name = model_name
        self.expected_dim = expected_dim
        self._cache: dict[str, List[float]] = {}
        self._cache_size = cache_size
        self._session: aiohttp.ClientSession | None = None
        self.logger = logging.getLogger(f"discord_bot.{self.__class__.__name__}")
        self.trace_logger = trace_logger
        self.provider = provider
        self.api_url = api_url

    async def initialize(self) -> None:
        """Hook for subclasses to validate config (e.g. API key). No-op by default."""
        return None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    def _cache_get(self, text: str) -> List[float] | None:
        return self._cache.get(text)

    def _cache_put(self, text: str, vector: List[float]) -> None:
        self._cache[text] = vector
        if len(self._cache) > self._cache_size:
            self._cache.pop(next(iter(self._cache)))

    def _fit_vector(self, vector: List[float]) -> List[float]:
        """Fit provider output to the configured vector size used by Redis."""
        expected = self.expected_dim
        if not expected or not vector or len(vector) == expected:
            return vector
        if len(vector) > expected:
            self.logger.warning(
                "Embedding dimension mismatch for %s: got %d, trimming to %d",
                self.model_name,
                len(vector),
                expected,
            )
            return vector[:expected]
        self.logger.warning(
            "Embedding dimension mismatch for %s: got %d, padding to %d",
            self.model_name,
            len(vector),
            expected,
        )
        return vector + [0.0] * (expected - len(vector))

    @staticmethod
    def _l2_norm(vector: List[float]) -> float:
        return math.sqrt(sum(x * x for x in vector))

    def _trace_embedding_event(
        self,
        *,
        input_text: str,
        vector: List[float],
        raw_dim: int | None,
        latency_ms: float,
        cache_hit: bool,
        event_type: str = "EMBED",
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
        """Emit a trace record if a trace logger is configured."""
        if self.trace_logger is None:
            return
        self.trace_logger.log(
            event_type=event_type,
            model_name=self.model_name,
            provider=self.provider,
            api_url=self.api_url,
            vector_dim=len(vector),
            raw_dim=raw_dim,
            l2_norm=self._l2_norm(vector) if vector else None,
            latency_ms=latency_ms,
            cache_hit=cache_hit,
            input_text=input_text,
            query_text=query_text,
            matched_text=matched_text,
            cosine_similarity=cosine_similarity,
            token_overlap=token_overlap,
            action=action,
            knn_score=knn_score,
            bm25_score=bm25_score,
            rrf_rank=rrf_rank,
            extra=extra,
        )

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    @abc.abstractmethod
    async def get_embedding(self, text: str) -> List[float]:
        """Return the embedding vector for `text`, or [] on empty/error."""
        ...
