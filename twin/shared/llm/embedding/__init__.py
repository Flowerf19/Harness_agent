"""Embedding services package.

Public API:
    create_embedding_service()  — factory, routes by EMBEDDING_PROVIDER
    BaseEmbeddingService        — ABC for custom providers
    OpenAIEmbeddingService      — OpenAI-compatible (covers Qwen, Voyage, ...)
    GeminiEmbeddingService      — native Gemini :embedContent
"""

from .base_embedding_service import BaseEmbeddingService
from .embedding_factory import create_embedding_service
from .gemini_embedding_service import GeminiEmbeddingService
from .openai_embedding_service import OpenAIEmbeddingService

__all__ = [
    "BaseEmbeddingService",
    "OpenAIEmbeddingService",
    "GeminiEmbeddingService",
    "create_embedding_service",
]
