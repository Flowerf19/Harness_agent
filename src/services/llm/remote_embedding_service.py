"""RemoteEmbeddingService - Gọi embedding qua API (Qwen/OpenAI-compatible)."""
import asyncio
import logging
from typing import List

import aiohttp

from src.config.settings import Config

logger = logging.getLogger(__name__)


class RemoteEmbeddingService:
    """Trạm nhúng vector từ xa, qua API OpenAI-compatible."""

    def __init__(
        self,
        model_name: str = "text-embedding-v3",
        api_key: str = None,
        api_url: str = None,
    ):
        self.model_name = model_name
        self.api_key = api_key or Config.EMBEDDING_API_KEY
        self.api_url = (api_url or Config.EMBEDDING_API_URL).rstrip("/")
        self._session = None
        self._cache = {}

    async def initialize(self):
        if not self.api_key:
            logger.warning("RemoteEmbeddingService: No API key configured")

    async def _get_session(self):
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
                    logger.error(f"Embedding API error ({response.status}): {error_text}")
                    return []

                data = await response.json()
                vector = data["data"][0]["embedding"]

                self._cache[text] = vector
                if len(self._cache) > 100:
                    self._cache.pop(next(iter(self._cache)))

                return vector

        except Exception as e:
            logger.error(f"RemoteEmbeddingService error: {e}")
            return []

    async def close(self):
        if self._session:
            await self._session.close()
