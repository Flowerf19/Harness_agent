import sys

sys.path.insert(0, "/home/flowerf/Projects/Arize_Phoenix_tool_kit")
import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List

from phoenix_core import track_rag_step

logger = logging.getLogger(__name__)


class MessageCategory(Enum):
    FACT = "fact"
    PREFERENCE = "preference"
    QUERY = "query"
    RESPONSE = "response"
    RELATIONSHIP = "relationship"
    GOAL = "goal"
    STATUS_UPDATE = "status_update"
    GENERAL = "general"


@dataclass
class WorkingMemoryEntry:
    role: str  # 'user' or 'assistant'
    content: str
    timestamp: datetime
    importance_score: float = 0.5  # 0.0 - 1.0
    category: MessageCategory = MessageCategory.GENERAL
    access_count: int = 0
    is_sensitive: bool = False


class ContextManager:
    """
    Service for managing working memory context window.
    Handles basic memory operations like adding, clearing, and managing memory entries.
    """

    def __init__(self, max_capacity: int = 20, trigger_threshold: int = 20):
        self.max_capacity = max_capacity
        self.trigger_threshold = trigger_threshold
        self.memories: Dict[str, List[WorkingMemoryEntry]] = {}
        self.trigger_callbacks = []

        # Persistent storage configuration
        self.data_dir = Path("data/user_summaries")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.history_lock = asyncio.Lock()

    @track_rag_step(
        name="working_memory.context_manager.add_message",
        metadata={
            "service": "working_memory",
            "component": "context_manager",
            "operation": "add_message",
        },
    )
    def add_message(self, user_id: str, role: str, content: str) -> WorkingMemoryEntry:
        """
        Add a message to working memory with importance evaluation.
        """
        entry = WorkingMemoryEntry(
            role=role,
            content=content,
            timestamp=datetime.now(),
            importance_score=0.5,  # Will be set by PriorityQueue
            category=MessageCategory.GENERAL,  # Will be set by PriorityQueue
        )

        # Add to user's memory list
        if user_id not in self.memories:
            self.memories[user_id] = []

        self.memories[user_id].append(entry)

        # Check trigger conditions
        self._check_trigger_conditions(user_id)

        logger.debug(
            f"📥 Added message to working memory for {user_id}: {content[:50]}..."
        )

        return entry

    def _check_trigger_conditions(self, user_id: str):
        """
        Check conditions to trigger callbacks.
        """
        if user_id not in self.memories:
            return

        message_count = len(self.memories[user_id])

        # Trigger if message count reaches threshold
        if message_count >= self.trigger_threshold:
            self._trigger_callback("MESSAGE_THRESHOLD_REACHED", user_id, message_count)

    def register_trigger_callback(self, callback_func):
        """
        Register a callback function for triggers.
        """
        self.trigger_callbacks.append(callback_func)

    def _trigger_callback(self, trigger_type: str, user_id: str, data: any):
        """
        Trigger registered callbacks.
        """
        for callback in self.trigger_callbacks:
            try:
                callback(trigger_type, user_id, data)
            except Exception as e:
                logger.error(f"Error in trigger callback: {e}")

    def cleanup_old_entries(self, user_id: str, max_entries: int = 50) -> int:
        """
        Clean up old entries using FIFO algorithm.
        Keeps only the N most recent entries by timestamp.
        """
        if user_id not in self.memories:
            return 0

        user_memory = self.memories[user_id]

        if len(user_memory) <= max_entries:
            return 0

        # Sort by timestamp, newest at the end
        sorted_entries = sorted(user_memory, key=lambda x: x.timestamp.timestamp())

        # Keep the N newest entries (at the end)
        entries_to_keep = sorted_entries[-max_entries:]

        # Update working memory
        self.memories[user_id] = entries_to_keep

        deleted_count = len(user_memory) - max_entries

        logger.debug(
            f"🧹 Cleaned up working memory for {user_id}, kept {len(self.memories[user_id])} entries, deleted {deleted_count} entries"
        )

        return deleted_count

    def get_statistics(self, user_id: str) -> Dict:
        """
        Get statistics about user's working memory.
        """
        if user_id not in self.memories:
            return {
                "total_messages": 0,
                "categories": {},
                "avg_importance": 0.0,
            }

        user_memory = self.memories[user_id]

        # Category statistics
        categories = {}
        total_importance = 0

        for entry in user_memory:
            # Category stats
            cat = entry.category.value
            categories[cat] = categories.get(cat, 0) + 1

            # Total importance
            total_importance += entry.importance_score

        # Average importance
        avg_importance = total_importance / len(user_memory) if user_memory else 0.0

        return {
            "total_messages": len(user_memory),
            "categories": categories,
            "avg_importance": round(avg_importance, 2),
        }

    def clear_memory(self, user_id: str):
        """
        Clear all working memory for a user.
        """
        if user_id in self.memories:
            del self.memories[user_id]
            logger.info(f"🗑️ Cleared working memory for {user_id}")

    async def _get_history_path(self, user_id: str) -> Path:
        """Get the history file path for a user."""
        return self.data_dir / f"{user_id}_history.json"

    async def save_to_persistent_history(self, user_id: str, messages: list):
        """
        Save messages to history file with lock to prevent conflicts.
        """
        async with self.history_lock:
            history = await self.get_persistent_history(user_id)
            history.extend(messages)

            # Limit history size (FIFO)
            max_history = 1000
            if len(history) > max_history:
                history = history[-max_history:]

            file_path = await self._get_history_path(user_id)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)

    async def append_message_to_persistent_history(self, user_id: str, message: dict):
        """
        Append a single message to history.
        """
        await self.save_to_persistent_history(user_id, [message])

    async def get_persistent_history(self, user_id: str) -> list:
        """
        Read history from file.
        Returns saved messages list, or [] if file doesn't exist.
        """
        async with self.history_lock:
            file_path = await self._get_history_path(user_id)
            if not file_path.exists():
                return []

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                return []

    def get_persistent_history_sync(self, user_id: str) -> list:
        """
        Read history from file (sync version).
        """
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(self.get_persistent_history(user_id))
                loop.close()
                return result
            else:
                return asyncio.run(self.get_persistent_history(user_id))
        except RuntimeError:
            return asyncio.run(self.get_persistent_history(user_id))

    def save_to_persistent_history_sync(self, user_id: str, messages: list):
        """
        Save messages to history file (sync version).
        """
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(
                    self.save_to_persistent_history(user_id, messages)
                )
                loop.close()
            else:
                asyncio.run(self.save_to_persistent_history(user_id, messages))
        except RuntimeError:
            asyncio.run(self.save_to_persistent_history(user_id, messages))

    def append_message_to_persistent_history_sync(self, user_id: str, message: dict):
        """
        Append a single message to history (sync version).
        """
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(
                    self.append_message_to_persistent_history(user_id, message)
                )
                loop.close()
            else:
                asyncio.run(self.append_message_to_persistent_history(user_id, message))
        except RuntimeError:
            asyncio.run(self.append_message_to_persistent_history(user_id, message))
