# src/services/memories/core_memory/__init__.py
"""
Core Memory Module.
Provides structured, persistent memory storage for essential user information.

Main components:
- Models: CoreMemoryRecord for structured core memory data
- Manager: CoreManager for CRUD operations
- Storage: BaseCoreDB, LocalCoreDB for persistence
"""

from .core_manager import CoreManager
from .models import UserProfile
from .storage import BaseCoreDB, LocalCoreDB

__all__ = [
    # Models
    "UserProfile",
    # Manager
    "CoreManager",
    # Storage
    "BaseCoreDB",
    "LocalCoreDB",
]
