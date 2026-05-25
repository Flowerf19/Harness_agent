"""Abstract base for embedding services (OpenAI-compat, Gemini, ...)."""

from __future__ import annotations

import abc
import logging
from typing import List

import aiohttp


class BaseEmbeddingService(abc.ABC):
    """
    Common interface for all embedding providers.

    Subclasses implement `get_embedding(text)` against a specific provider's
    HTTP protocol. Shared concerns (aiohttp session, in-memory LRU cache,
    cleanup) live here so providers stay focused on payload shape.
    """

    def __init__(self, model_name: str, *, cache_size: int = 100):
        self.model_name = model_name
        self._cache: dict[str, List[float]] = {}
        self._cache_size = cache_size
        self._session: aiohttp.ClientSession | None = None
        self.logger = logging.getLogger(f"discord_bot.{self.__class__.__name__}")

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

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    @abc.abstractmethod
    async def get_embedding(self, text: str) -> List[float]:
        """Return the embedding vector for `text`, or [] on empty/error."""
        ...
