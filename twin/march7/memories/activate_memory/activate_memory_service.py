import logging
from typing import Dict, List

from langsmith import traceable

from .constants import KEEP_RECENT_MESSAGES_AFTER_SUMMARY
from .events.event_dispatcher import EventDispatcher
from .management.context_builder import ContextBuilder
from .management.summary_policy import SummaryPolicy
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
        context_builder: ContextBuilder,
        event_dispatcher: EventDispatcher,
        summary_policy: SummaryPolicy,
    ):
        self.storage = storage
        self.token_counter = token_counter
        self.context_builder = context_builder
        self.events = event_dispatcher
        self.summary_policy = summary_policy

    @traceable(
        name="T1_Process_New_Message", run_type="chain", tags=["tier_1", "core_flow"]
    )
    async def add_message(self, user_id: str, role: str, content: str) -> MemoryEntry:
        """Backward-compatible user-scope observe API."""
        return await self.observe_user_message(user_id=user_id, role=role, content=content)

    async def observe_user_message(
        self, user_id: str, role: str, content: str
    ) -> MemoryEntry:
        """Observe a standard 1-1 user message."""
        tokens = self.token_counter.count_entry_tokens(content)
        entry = MemoryEntry(
            scope="user",
            scope_id=user_id,
            user_id=user_id,
            role=role,
            content=content,
            tokens=tokens,
        )
        await self.storage.save_entry(entry)
        await self.summary_policy.state_repo.record_entry("user", user_id, tokens)
        await self.summary_policy.evaluate("user", user_id)

        logger.debug("📥 ActiveMemory: Saved user message (User: %s | Tokens: %s)", user_id, tokens)
        return entry

    async def observe_channel_message(
        self,
        guild_id: str,
        channel_id: str,
        author_id: str,
        author_name: str,
        message_id: str,
        content: str,
        reply_to: str | None = None,
    ) -> MemoryEntry:
        """Observe channel discussion without implying a bot response."""
        tokens = self.token_counter.count_entry_tokens(content)
        entry = MemoryEntry(
            scope="channel",
            scope_id=channel_id,
            user_id=author_id,
            role="user",
            author_id=author_id,
            author_name=author_name,
            guild_id=guild_id,
            channel_id=channel_id,
            message_id=message_id,
            reply_to=reply_to,
            content=content,
            tokens=tokens,
        )
        await self.storage.save_entry(entry)
        await self.summary_policy.state_repo.record_entry("channel", channel_id, tokens)
        await self.summary_policy.evaluate("channel", channel_id)

        logger.debug("📥 ActiveMemory: Saved channel message (Channel: %s | Tokens: %s)", channel_id, tokens)
        return entry

    @traceable(
        name="T1_Get_Context_For_LLM",
        run_type="chain",
        tags=["tier_1", "active_memory", "read", "context_assembly"]
    )
    async def get_context_for_llm(self, user_id: str) -> List[Dict]:
        """Get context for LLM prompt."""
        entries = await self.storage.get_entries("user", user_id)
        return self.context_builder.build_context(entries)

    async def reset_session(self, user_id: str):
        """Clear all entries for user."""
        await self.storage.clear_all("user", user_id)

    async def cleanup_summarized(
        self,
        scope: str,
        scope_id: str,
        summarized_entry_ids: List[str],
        keep_recent: int = KEEP_RECENT_MESSAGES_AFTER_SUMMARY,
    ) -> None:
        """Cleanup raw entries after T2 confirms summary completion."""
        entries = await self.storage.get_entries(scope, scope_id)
        entries.sort(key=lambda e: e.timestamp)
        recent_ids = {e.entry_id for e in entries[-keep_recent:]}
        ids_to_delete = [
            entry_id for entry_id in summarized_entry_ids if entry_id not in recent_ids
        ]
        if ids_to_delete:
            await self.storage.delete_entries(scope, scope_id, ids_to_delete)
