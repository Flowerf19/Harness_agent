"""OpenAIEmbeddingService - Call embeddings via an OpenAI-compatible API."""

import logging
from typing import List

import aiohttp

from twin.shared.config.settings import Config

logger = logging.getLogger(__name__)


class OpenAIEmbeddingService:
    """Remote embeddings via an OpenAI-compatible API (POST /embeddings)."""

    def __init__(
        self,
        model_name: str = "text-embedding-v3",
        api_key: str | None = None,
        api_url: str | None = None,
    ):
        self.model_name = model_name
        self.api_key = api_key or Config.EMBEDDING_API_KEY
        self.api_url = (api_url or Config.EMBEDDING_API_URL).rstrip("/")
        self._session: aiohttp.ClientSession | None = None
        self._cache: dict[str, List[float]] = {}

    async def initialize(self):
        if not self.api_key:
            logger.warning("OpenAIEmbeddingService: No API key configured")

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    async def get_embedding(self, text: str) -> List[float]:
        if not text or not text.strip():
            return []

        if text in self._cache:
            return self._cache[text]

        try:
            session = await self._get_session()
            async with session.post(
                f"{self.api_url}/embeddings",
                json={
                    "model": self.model_name,
                    "input": text,
                },
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(
                        "Embedding API error (%s): %s", response.status, error_text
                    )
                    return []

                data = await response.json()
                vector = data["data"][0]["embedding"]

                self._cache[text] = vector
                if len(self._cache) > 100:
                    self._cache.pop(next(iter(self._cache)))

                return vector

        except Exception as e:
            logger.error("OpenAIEmbeddingService error: %s", e)
            return []

    async def close(self):
        if self._session:
            await self._session.close()
