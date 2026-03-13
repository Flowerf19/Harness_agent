# src/services/memories/episodic_memory/__init__.py
"""
Episodic Memory Module.
Provides long-term memory storage and retrieval using vector embeddings.

Main components:
- Models: EpisodicPayload, EpisodicRecord for structured memory data
- Extraction: EventExtractor, VectorEngine, ContextFormatter for processing
- Storage: BaseVectorDB, LocalVectorDB for persistence
"""

from .extraction import ContextFormatter, EventExtractor, VectorEngine
from .models import EpisodicPayload, EpisodicRecord, get_utc_now
from .storage import BaseVectorDB, LocalVectorDB

__all__ = [
    # Models
    "EpisodicPayload",
    "EpisodicRecord",
    "get_utc_now",
    # Extraction
    "EventExtractor",
    "VectorEngine",
    "ContextFormatter",
    # Storage
    "BaseVectorDB",
    "LocalVectorDB",
]
