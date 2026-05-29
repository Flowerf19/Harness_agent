"""Idle summary adapter for shared ActiveMemory."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Awaitable, Callable

from twin.shared.memory.active.constants import IDLE_TRIGGER_MINUTES, TOKEN_THRESHOLD
from twin.shared.memory.active.service import ActiveMemory

logger = logging.getLogger(__name__)

TriggerCallback = Callable[[str, str], Awaitable[dict | None] | Awaitable[None]]


class ActiveSummaryStateRepository:
    """Small adapter consumed by the existing InactivityTrigger."""

    def __init__(self, active: ActiveMemory) -> None:
        self.active = active

    async def list_active(self, scope: str) -> list[str]:
        return await self.active.store.list_active_scope_ids(scope)

    async def mark_completed(self, payload: dict) -> None:
        return None

    async def mark_failed(self, payload: dict) -> None:
        return None


class ActiveSummaryPolicy:
    """Evaluate idle/token triggers over ActiveStore state."""

    def __init__(
        self,
        active: ActiveMemory,
        trigger_callback: TriggerCallback,
        *,
        idle_minutes: int = IDLE_TRIGGER_MINUTES,
    ) -> None:
        self.active = active
        self.trigger_callback = trigger_callback
        self.idle_seconds = idle_minutes * 60
        self._in_progress: set[tuple[str, str]] = set()

    async def evaluate(self, scope: str, scope_id: str) -> None:
        key = (scope, scope_id)
        if key in self._in_progress:
            return
        state = await self.active.store.get_state(scope, scope_id)
        tokens = int(state.get("unsummarized_tokens") or 0)
        if tokens <= 0:
            return

        should_trigger = tokens >= TOKEN_THRESHOLD
        last_entry_ts = state.get("last_entry_ts")
        if not should_trigger and last_entry_ts:
            idle_for = datetime.now(timezone.utc).timestamp() - float(last_entry_ts)
            should_trigger = idle_for >= self.idle_seconds
        if not should_trigger:
            return

        self._in_progress.add(key)
        try:
            logger.info("T1: summary policy triggering scope=%s/%s", scope, scope_id)
            await self.trigger_callback(scope, scope_id)
        finally:
            self._in_progress.discard(key)
