import logging
from typing import Dict, List

from langsmith import traceable

from .constants import MAX_WORKING_TOKENS
from .events.event_dispatcher import ActiveMemoryEvent, EventDispatcher
from .management.context_builder import ContextBuilder
from .management.smart_cleanup import SmartCleanup
from .management.token_counter import TokenCounter
from .models import MemoryEntry
from .storage.base_storage import BaseStorage

logger = logging.getLogger(__name__)


class ActiveMemoryService:
    """T1 Active Memory Service - Manages short-term conversation memory."""

    def __init__(
        self,
        storage: BaseStorage,
        token_counter: TokenCounter,
        smart_cleanup: SmartCleanup,
        context_builder: ContextBuilder,
        event_dispatcher: EventDispatcher,
    ):
        self.storage = storage
        self.token_counter = token_counter
        self.smart_cleanup = smart_cleanup
        self.context_builder = context_builder
        self.events = event_dispatcher

    @traceable(
        name="T1_Process_New_Message", run_type="chain", tags=["tier_1", "core_flow"]
    )
    async def add_message(self, user_id: str, role: str, content: str) -> MemoryEntry:
        """Process new message: Count tokens, store, emit overflow event if threshold reached."""

        # 1. Count tokens
        tokens = self.token_counter.count_entry_tokens(content)

        # 2. Create entry
        entry = MemoryEntry(
            user_id=user_id,
            role=role,
            content=content,
            tokens=tokens,
        )

        # 3. Save to storage
        await self.storage.save_entry(entry)

        # 4. Check overflow threshold
        current_tokens = await self.storage.get_total_tokens(user_id)
        if current_tokens >= MAX_WORKING_TOKENS:
            snapshot = await self.storage.get_entries(user_id)
            self.events.emit(
                ActiveMemoryEvent.TOKEN_LIMIT_REACHED,
                user_id,
                data={"snapshot": snapshot, "current_tokens": current_tokens},
            )

        logger.debug(
            f"📥 ActiveMemory: Saved message (User: {user_id} | Tokens: {current_tokens}/{MAX_WORKING_TOKENS})"
        )
        return entry

    @traceable(
        name="T1_Get_Context_For_LLM",
        run_type="chain",
        tags=["tier_1", "active_memory", "read", "context_assembly"]
    )
    async def get_context_for_llm(self, user_id: str) -> List[Dict]:
        """Get context for LLM prompt."""
        entries = await self.storage.get_entries(user_id)
        return self.context_builder.build_context(entries)

    async def force_cleanup(self, user_id: str):
        """Cleanup after T2 consolidation completes."""
        current_tokens = await self.storage.get_total_tokens(user_id)
        await self.smart_cleanup.execute(user_id, current_tokens)

    async def reset_session(self, user_id: str):
        """Clear all entries for user."""
        await self.storage.clear_all(user_id)
