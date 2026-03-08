# src/services/memories/core_memory/__init__.py
"""
Core Memory Module.
Provides structured, persistent memory storage for essential user information.

Main components:
- Models: CoreMemoryRecord for structured core memory data
- Manager: CoreMemoryManager for CRUD operations
- Storage: BaseCoreDB, LocalJSONDB for persistence
"""

from .core_manager import CoreMemoryManager
from .models import CoreMemoryRecord
from .prompts import CORE_MEMORY_EXTRACTION_PROMPT
from .storage import BaseCoreDB, LocalJSONDB

__all__ = [
    # Models
    "CoreMemoryRecord",
    # Prompts
    "CORE_MEMORY_EXTRACTION_PROMPT",
    # Manager
    "CoreMemoryManager",
    # Storage
    "BaseCoreDB",
    "LocalJSONDB",
]
