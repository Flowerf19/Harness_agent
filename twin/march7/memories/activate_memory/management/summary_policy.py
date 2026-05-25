from datetime import timedelta
from typing import Any

from ..constants import (
    CHANNEL_SUMMARY_TOKEN_LIMIT,
    MAX_WORKING_TOKENS,
    SUMMARY_IDLE_MINUTES,
    SUMMARY_LOCK_TTL_MINUTES,
    SUMMARY_MAX_MESSAGES,
    SUMMARY_MIN_MESSAGES,
)
from ..events.event_dispatcher import ActiveMemoryEvent, EventDispatcher
from ..models import MemoryEntry, get_utc_now
from ..storage.base_storage import BaseStorage
from .state_repository import SummaryStateRepository


class SummaryPolicy:
    def __init__(
        self,
        storage: BaseStorage,
        state_repo: SummaryStateRepository,
        event_dispatcher: EventDispatcher,
    ):
        self.storage = storage
        self.state_repo = state_repo
        self.events = event_dispatcher

    async def evaluate(self, scope: str, scope_id: str) -> None:
        state = await self.state_repo.get(scope, scope_id)
        now = get_utc_now()
        if state.summary_in_progress and state.locked_until and now < state.locked_until:
            return
        if state.locked_until and now < state.locked_until and not state.summary_in_progress:
            return

        reason = self._check_trigger(state, scope)
        if not reason:
            return

        entries = await self.storage.get_entries(scope, scope_id)
        if not entries:
            return

        payload = self._build_payload(scope, scope_id, entries, reason)
        await self.state_repo.set_in_progress(scope, scope_id, SUMMARY_LOCK_TTL_MINUTES)
        self.events.emit(ActiveMemoryEvent.SUMMARY_REQUESTED, scope_id, data=payload)

    def _check_trigger(self, state: Any, scope: str) -> str | None:
        token_limit = (
            CHANNEL_SUMMARY_TOKEN_LIMIT if scope == "channel" else MAX_WORKING_TOKENS
        )
        if state.unsummarized_token_count >= token_limit:
            return "token_limit"
        if state.unsummarized_message_count >= SUMMARY_MAX_MESSAGES:
            return "message_count"
        idle_for = get_utc_now() - state.last_activity_at
        if (
            idle_for >= timedelta(minutes=SUMMARY_IDLE_MINUTES)
            and state.unsummarized_message_count >= SUMMARY_MIN_MESSAGES
        ):
            return "idle"
        return None

    def _build_payload(
        self, scope: str, scope_id: str, entries: list[MemoryEntry], reason: str
    ) -> dict:
        entries = sorted(entries, key=lambda e: e.timestamp)
        first = entries[0]
        last = entries[-1]
        return {
            "scope": scope,
            "scope_id": scope_id,
            "guild_id": last.guild_id,
            "channel_id": last.channel_id if scope == "channel" else None,
            "reason": reason,
            "from_entry_id": first.entry_id,
            "to_entry_id": last.entry_id,
            "from_ts": first.timestamp.isoformat(),
            "to_ts": last.timestamp.isoformat(),
            "message_count": len(entries),
            "token_count": sum(e.tokens for e in entries),
            "entries": [
                {
                    "entry_id": e.entry_id,
                    "message_id": e.message_id,
                    "author_id": e.author_id,
                    "author_name": e.author_name,
                    "user_id": e.user_id,
                    "role": e.role,
                    "content": e.content,
                    "timestamp": e.timestamp.isoformat(),
                    "reply_to": e.reply_to,
                }
                for e in entries
            ],
        }
