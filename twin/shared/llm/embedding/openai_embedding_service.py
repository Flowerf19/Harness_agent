"""OpenAIEmbeddingService — embeddings via an OpenAI-compatible API (POST /embeddings).

Works for OpenAI proper and any OpenAI-compatible vendor (Qwen/DashScope,
LM Studio, Voyage, Cohere v2-compat, OpenRouter, ...). Pick provider via
the URL/model/key passed to `__init__` or via the factory.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, List

from twin.shared.config.settings import Config
from .base_embedding_service import BaseEmbeddingService

if TYPE_CHECKING:
    from .embedding_trace_logger import EmbeddingTraceLogger


class OpenAIEmbeddingService(BaseEmbeddingService):
    """Remote embeddings via an OpenAI-compatible API (POST /embeddings)."""

    def __init__(
        self,
        model_name: str = "text-embedding-v3",
        api_key: str | None = None,
        api_url: str | None = None,
        expected_dim: int | None = None,
        trace_logger: EmbeddingTraceLogger | None = None,
        provider: str = "openai_compat",
    ):
        super().__init__(
            model_name=model_name,
            expected_dim=expected_dim or Config.EMBEDDING_VECTOR_SIZE,
            trace_logger=trace_logger,
            provider=provider,
            api_url=(api_url or Config.EMBEDDING_API_URL).rstrip("/"),
        )
        self.api_key = api_key or Config.EMBEDDING_API_KEY

    async def initialize(self) -> None:
        if not self.api_key:
            self.logger.warning("OpenAIEmbeddingService: No API key configured")

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

        started_at = time.perf_counter()
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.api_url}/embeddings",
                json={"model": self.model_name, "input": text},
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    self.logger.error(
                        "Embedding API error (%s): %s", response.status, error_text
                    )
                    return []

                data = await response.json()
                raw_vector = data["data"][0]["embedding"]
                raw_dim = len(raw_vector)
                vector = self._fit_vector(raw_vector)
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
            self.logger.error("OpenAIEmbeddingService error: %s", e)
            return []
