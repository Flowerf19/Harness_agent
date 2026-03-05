import sys

sys.path.insert(0, "/home/flowerf/Projects/Arize_Phoenix_tool_kit")
import logging
from datetime import datetime
from enum import Enum
from typing import Dict, List

from phoenix_core import track_rag_step

from src.services.working_memory.context_manager import (
    MessageCategory,
    WorkingMemoryEntry,
)

logger = logging.getLogger(__name__)


class ContextBuilder:
    """
    Service for building context from working memory entries.
    Handles different context retrieval strategies based on user needs.
    """

    def __init__(self):
        pass

    @track_rag_step(
        name="working_memory.context_builder.build_context",
        metadata={
            "service": "working_memory",
            "component": "context_builder",
            "operation": "build_context",
        },
    )
    def get_context(
        self,
        memories: Dict[str, List[WorkingMemoryEntry]],
        user_id: str,
        max_entries: int = 5,
    ) -> List[WorkingMemoryEntry]:
        """
        Get chronological context from working memory.
        Returns messages in chronological order (oldest to newest).
        """
        if user_id not in memories or not memories[user_id]:
            return []

        # Get user's memory entries
        user_memory = memories[user_id]

        # Sort by timestamp to ensure chronological order
        sorted_entries = sorted(user_memory, key=lambda x: x.timestamp.timestamp())

        # Get the latest N entries (at the end of the sorted list)
        if len(sorted_entries) > max_entries:
            chronological_entries = sorted_entries[-max_entries:]
        else:
            chronological_entries = sorted_entries

        return chronological_entries

    @track_rag_step(
        name="working_memory.context_builder.get_recent_conversation",
        metadata={
            "service": "working_memory",
            "component": "context_builder",
            "operation": "get_recent_conversation",
        },
    )
    def get_recent_conversation(
        self,
        memories: Dict[str, List[WorkingMemoryEntry]],
        user_id: str,
        max_entries: int = 3,
    ) -> List[WorkingMemoryEntry]:
        """
        Get recent conversation entries in chronological order.
        Increments access count for retrieved entries.
        """
        if user_id not in memories or not memories[user_id]:
            return []

        # Get the most recent entries
        user_memory = memories[user_id]
        recent_entries = user_memory[-max_entries:]  # Get from the end of the list

        # Increment access count for these entries
        for entry in recent_entries:
            entry.access_count += 1

        return recent_entries

    @track_rag_step(
        name="working_memory.context_builder.search_by_category",
        metadata={
            "service": "working_memory",
            "component": "context_builder",
            "operation": "search_by_category",
        },
    )
    def search_by_category(
        self,
        memories: Dict[str, List[WorkingMemoryEntry]],
        user_id: str,
        category: MessageCategory,
        limit: int = 5,
    ) -> List[WorkingMemoryEntry]:
        """
        Search for entries by category.
        Returns entries sorted by importance score and timestamp (highest first).
        """
        if user_id not in memories:
            return []

        matching_entries = [
            entry for entry in memories[user_id] if entry.category == category
        ]

        # Sort by importance score and timestamp (highest first)
        sorted_entries = sorted(
            matching_entries,
            key=lambda x: (x.importance_score, x.timestamp.timestamp()),
            reverse=True,
        )

        return sorted_entries[:limit]
