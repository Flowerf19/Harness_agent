"""Factory for embedding services.

Centralises provider selection so containers don't carry their own routing
logic. Pick the provider via `EMBEDDING_PROVIDER` env (or explicit arg).

Supported providers:
- openai / openai_compat / qwen -> OpenAIEmbeddingService
  (Qwen DashScope, LM Studio, Voyage, OpenRouter, etc. all fit here —
   they're OpenAI-compatible. Switch by setting EMBEDDING_API_URL/KEY/MODEL.)
- gemini / google -> GeminiEmbeddingService
"""

from __future__ import annotations

import os

from twin.shared.config.settings import Config
from .base_embedding_service import BaseEmbeddingService
from .gemini_embedding_service import GeminiEmbeddingService
from .openai_embedding_service import OpenAIEmbeddingService

_OPENAI_ALIASES = {
    "openai",
    "openai_compat",
    "openai-compatible",
    "openai_compatible",
    "qwen",
}
_GEMINI_ALIASES = {"gemini", "google"}


def create_embedding_service(
    provider: str | None = None,
    *,
    model_name: str | None = None,
    api_key: str | None = None,
    api_url: str | None = None,
) -> BaseEmbeddingService:
    """Construct an embedding service for `provider` (defaults to env config)."""
    resolved = (provider or getattr(Config, "EMBEDDING_PROVIDER", "openai_compat")).lower()

    if resolved in _OPENAI_ALIASES:
        return OpenAIEmbeddingService(
            model_name=model_name or Config.EMBEDDING_MODEL_NAME,
            api_key=api_key or Config.EMBEDDING_API_KEY,
            api_url=api_url or Config.EMBEDDING_API_URL,
            expected_dim=Config.EMBEDDING_VECTOR_SIZE,
        )

    if resolved in _GEMINI_ALIASES:
        return GeminiEmbeddingService(
            model_name=model_name or os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"),
            api_key=api_key or os.getenv("GEMINI_API_KEY"),
            api_url=api_url or os.getenv(
                "GEMINI_EMBEDDING_API_URL",
                "https://generativelanguage.googleapis.com/v1beta/models",
            ),
            output_dimensionality=getattr(Config, "EMBEDDING_VECTOR_SIZE", None),
            expected_dim=Config.EMBEDDING_VECTOR_SIZE,
        )

    raise ValueError(
        f"Unsupported embedding provider: {resolved!r}. "
        "Supported: openai_compat (alias: openai, qwen), gemini."
    )
