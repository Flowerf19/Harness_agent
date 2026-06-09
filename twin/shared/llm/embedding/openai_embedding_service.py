"""OpenAIEmbeddingService — embeddings via an OpenAI-compatible API (POST /embeddings).

Works for OpenAI proper and any OpenAI-compatible vendor (Qwen/DashScope,
LM Studio, Voyage, Cohere v2-compat, OpenRouter, ...). Pick provider via
the URL/model/key passed to `__init__` or via the factory.
"""

from __future__ import annotations

from typing import List

from twin.shared.config.settings import Config
from .base_embedding_service import BaseEmbeddingService


class OpenAIEmbeddingService(BaseEmbeddingService):
    """Remote embeddings via an OpenAI-compatible API (POST /embeddings)."""

    def __init__(
        self,
        model_name: str = "text-embedding-v3",
        api_key: str | None = None,
        api_url: str | None = None,
        expected_dim: int | None = None,
    ):
        super().__init__(
            model_name=model_name,
            expected_dim=expected_dim or Config.EMBEDDING_VECTOR_SIZE,
        )
        self.api_key = api_key or Config.EMBEDDING_API_KEY
        self.api_url = (api_url or Config.EMBEDDING_API_URL).rstrip("/")

    async def initialize(self) -> None:
        if not self.api_key:
            self.logger.warning("OpenAIEmbeddingService: No API key configured")

    async def get_embedding(self, text: str) -> List[float]:
        if not text or not text.strip():
            return []

        cached = self._cache_get(text)
        if cached is not None:
            return cached

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
                vector = self._fit_vector(data["data"][0]["embedding"])
                self._cache_put(text, vector)
                return vector

        except Exception as e:
            self.logger.error("OpenAIEmbeddingService error: %s", e)
            return []
