"""ActiveMemory facade — orchestrates observe/get_context/trim + thresholds."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Awaitable, Callable

from twin.shared.memory.active.constants import (
    KEEP_RECENT_MESSAGES_AFTER_SUMMARY,
    RECENT_CATALOGS_WINDOW,
    TOKEN_THRESHOLD,
    TOPIC_SHIFT_MIN_CONFIDENCE,
    TOPIC_SHIFT_MIN_STABLE_TURNS,
)
from twin.shared.memory.active.detector import FastPathDetector
from twin.shared.memory.active.models import ActiveEntry
from twin.shared.memory.active.store import ActiveStore

logger = logging.getLogger(__name__)

TokenCounter = Callable[[str], int]
TriggerCallback = Callable[[str, str], Awaitable[None]]


def _default_token_counter(content: str) -> int:
    return len(content.split())


class ActiveMemory:
    """High-level T1 facade."""

    def __init__(
        self,
        store: ActiveStore,
        detector: FastPathDetector,
        token_counter: TokenCounter | None = None,
        trigger_callback: TriggerCallback | None = None,
    ) -> None:
        self.store = store
        self.detector = detector
        self.token_counter = token_counter or _default_token_counter
        self.trigger_callback = trigger_callback

    async def observe(
        self,
        scope: str,
        scope_id: str,
        role: str,
        content: str,
        *,
        author_id: str | None = None,
        author_name: str | None = None,
        message_id: str | None = None,
        guild_id: str | None = None,
        channel_id: str | None = None,
        reply_to: str | None = None,
    ) -> ActiveEntry:
        tokens = int(self.token_counter(content))
        entry = ActiveEntry(
            scope=scope,
            scope_id=scope_id,
            role=role,
            author_id=author_id,
            author_name=author_name,
            message_id=message_id,
            guild_id=guild_id,
            channel_id=channel_id,
            reply_to=reply_to,
            content=content,
            tokens=tokens,
        )
        await self.store.save(entry)

        state = await self.store.get_state(scope, scope_id)
        new_total = state["unsummarized_tokens"] + tokens
        await self.store.update_state(
            scope,
            scope_id,
            unsummarized_tokens=new_total,
            last_entry_ts=entry.created_at.timestamp(),
        )

        if role == "user":
            hit = self.detector.is_critical(content)
            if hit:
                logger.info(
                    "T1: fast-path catalog hit=%s scope=%s/%s entry=%s",
                    hit,
                    scope,
                    scope_id,
                    entry.entry_id,
                )

        if new_total >= TOKEN_THRESHOLD and self.trigger_callback is not None:
            logger.info(
                "T1: threshold reached (%d>=%d) scope=%s/%s — triggering consolidator",
                new_total,
                TOKEN_THRESHOLD,
                scope,
                scope_id,
            )
            await self.trigger_callback(scope, scope_id)

        return entry

    async def get_context(
        self, scope: str, scope_id: str, *, limit: int = 50
    ) -> list[ActiveEntry]:
        return await self.store.list_entries(scope, scope_id, limit=limit)

    async def trim(
        self,
        scope: str,
        scope_id: str,
        summarized_entry_ids: list[str],
        *,
        keep_recent: int = KEEP_RECENT_MESSAGES_AFTER_SUMMARY,
    ) -> None:
        if not summarized_entry_ids:
            return
        all_entries = await self.store.list_entries(scope, scope_id, limit=10_000)
        if not all_entries:
            return
        # Keep the N most recent entries no matter what.
        keep_ids = {e.entry_id for e in all_entries[-keep_recent:]} if keep_recent > 0 else set()
        to_delete = [eid for eid in summarized_entry_ids if eid not in keep_ids]
        if to_delete:
            await self.store.delete_entries(scope, scope_id, to_delete)

        remaining = [e for e in all_entries if e.entry_id not in set(to_delete)]
        # Count only tokens that are genuinely UN-summarized: exclude entries we
        # just summarized but physically retained for context (the keep_recent
        # tail). Entries that arrived after the consolidation snapshot are not in
        # summarized_entry_ids, so they still count — keeping the scope hot until
        # they too get summarized.
        summarized_set = set(summarized_entry_ids)
        remaining_tokens = sum(
            e.tokens for e in remaining if e.entry_id not in summarized_set
        )
        await self.store.update_state(
            scope, scope_id, unsummarized_tokens=remaining_tokens
        )
        logger.info(
            "T1: trim scope=%s/%s deleted=%d remaining_tokens=%d",
            scope,
            scope_id,
            len(to_delete),
            remaining_tokens,
        )

    async def reset_scope(self, scope: str, scope_id: str) -> None:
        await self.store.clear_scope(scope, scope_id)
        logger.info("T1: reset scope=%s/%s", scope, scope_id)

    async def push_catalog(
        self, scope: str, scope_id: str, catalog: str, confidence: float
    ) -> bool:
        """Append catalog to rolling window. Returns True if this is a topic shift."""
        state = await self.store.get_state(scope, scope_id)
        recent: list[str] = list(state.get("recent_catalogs") or [])
        shift = self.is_topic_shift(recent, catalog, confidence)
        recent.append(catalog)
        if len(recent) > RECENT_CATALOGS_WINDOW:
            recent = recent[-RECENT_CATALOGS_WINDOW:]
        await self.store.update_state(scope, scope_id, recent_catalogs=recent)
        if shift:
            logger.info("T1: topic shift detected scope=%s/%s -> %s", scope, scope_id, catalog)
        return shift

    @staticmethod
    def is_topic_shift(
        recent_catalogs: list[str], new_catalog: str, new_confidence: float
    ) -> bool:
        if new_confidence < TOPIC_SHIFT_MIN_CONFIDENCE:
            return False
        if len(recent_catalogs) < TOPIC_SHIFT_MIN_STABLE_TURNS:
            return False
        last_n = recent_catalogs[-TOPIC_SHIFT_MIN_STABLE_TURNS:]
        if len(set(last_n)) == 1 and new_catalog != last_n[-1]:
            return True
        return False

    # Used by callers that want a fresh utc datetime without importing.
    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)
