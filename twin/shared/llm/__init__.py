"""LLM wrapper services module."""

from .base_llm_service import BaseLLMService
from .llm_response import LLMResponse


def __getattr__(name):
    _imports = {
        "LocalEmbeddingService": ".embedding_service",
        "RemoteEmbeddingService": ".remote_embedding_service",
        "GeminiService": ".gemini_service",
        "QwenService": ".qwen_service",
    }
    if name in _imports:
        import importlib
        mod = importlib.import_module(_imports[name], __package__)
        return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "BaseLLMService",
    "LocalEmbeddingService",
    "RemoteEmbeddingService",
    "GeminiService",
    "LLMResponse",
    "QwenService",
]
