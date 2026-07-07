"""GeminiEmbeddingService — embeddings via Google Generative Language API.

Uses the native `:embedContent` endpoint (different schema from OpenAI):
    POST {api_url}/{model}:embedContent?key={api_key}
    body:     {
                "content": {"parts": [{"text": "..."}]},
                "outputDimensionality": <int>   # optional, MRL truncation
              }
    response: {"embedding": {"values": [...]}}

`gemini-embedding-001` defaults to 3072-dim. When `output_dimensionality`
is set below 3072 the API truncates via Matryoshka Representation Learning;
per Google docs the result must be L2-normalised by the caller (only the
full 3072 vector is pre-normalised).
"""

from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING, List

from .base_embedding_service import BaseEmbeddingService

if TYPE_CHECKING:
    from .embedding_trace_logger import EmbeddingTraceLogger

_DEFAULT_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"
_DEFAULT_MODEL = "gemini-embedding-001"
_NATIVE_DIM = 3072


class GeminiEmbeddingService(BaseEmbeddingService):
    """Remote embeddings via Google's generative language API."""

    def __init__(
        self,
        model_name: str = _DEFAULT_MODEL,
        api_key: str | None = None,
        api_url: str | None = None,
        output_dimensionality: int | None = None,
        expected_dim: int | None = None,
        trace_logger: EmbeddingTraceLogger | None = None,
        provider: str = "gemini",
    ):
        super().__init__(
            model_name=model_name,
            expected_dim=expected_dim or output_dimensionality,
            trace_logger=trace_logger,
            provider=provider,
            api_url=(api_url or _DEFAULT_API_URL).rstrip("/"),
        )
        self.api_key = api_key
        self.output_dimensionality = output_dimensionality

    async def initialize(self) -> None:
        if not self.api_key:
            self.logger.warning("GeminiEmbeddingService: No API key configured")

    async def get_embedding(self, text: str) -> List[float]:
        if not text or not text.strip():
            return []

        cached = self._cache_get(text)
        if cached is not None:
            self._trace_embedding_event(
                input_text=text,
                vector=cached,
                raw_dim=None,
                latency_ms=0.0,
                cache_hit=True,
            )
            return cached

        body: dict = {"content": {"parts": [{"text": text}]}}
        if self.output_dimensionality:
            body["outputDimensionality"] = self.output_dimensionality

        started_at = time.perf_counter()
        try:
            session = await self._get_session()
            url = f"{self.api_url}/{self.model_name}:embedContent?key={self.api_key}"
            async with session.post(
                url,
                json=body,
                headers={"Content-Type": "application/json"},
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    self.logger.error(
                        "Gemini embedding API error (%s): %s", response.status, error_text
                    )
                    return []

                data = await response.json()
                vector = data.get("embedding", {}).get("values", [])
                if not vector:
                    self.logger.error("Gemini embedding response missing values: %s", data)
                    return []

                raw_dim = len(vector)
                if self.output_dimensionality and self.output_dimensionality < _NATIVE_DIM:
                    vector = _l2_normalize(vector)

                vector = self._fit_vector(vector)
                latency_ms = (time.perf_counter() - started_at) * 1000
                self._trace_embedding_event(
                    input_text=text,
                    vector=vector,
                    raw_dim=raw_dim,
                    latency_ms=latency_ms,
                    cache_hit=False,
                )
                self._cache_put(text, vector)
                return vector

        except Exception as e:
            self.logger.error("GeminiEmbeddingService error: %s", e)
            return []


def _l2_normalize(vec: List[float]) -> List[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0:
        return vec
    return [x / norm for x in vec]
