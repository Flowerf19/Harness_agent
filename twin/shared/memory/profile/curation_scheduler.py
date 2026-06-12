"""Per-user debounced scheduler for T3 profile auto-curation runs."""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from twin.shared.memory.profile.constants import PROFILE_CURATION_IDLE_SECONDS

logger = logging.getLogger(__name__)

# curate() returns a status dict; these are no-op outcomes not worth a log line.
_SKIP_STATUSES = {"skip_trivial", "skip_unchanged"}


class ProfileCurationScheduler:
    """Debounced fire-and-forget scheduler.

    Repeated `schedule(user_id)` calls within the debounce window collapse
    into a single curation run. A per-user lock prevents two curations from
    executing concurrently for the same user.
    """

    def __init__(
        self,
        curate_callable: Callable[[str], Awaitable[dict | None]],
        *,
        debounce_seconds: float = PROFILE_CURATION_IDLE_SECONDS,
    ) -> None:
        self._callable = curate_callable
        self._debounce = debounce_seconds
        self._pending: dict[str, asyncio.Task] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._closed = False

    def _lock_for(self, user_id: str) -> asyncio.Lock:
        lock = self._locks.get(user_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[user_id] = lock
        return lock

    def schedule(self, user_id: str) -> None:
        if self._closed:
            return
        existing = self._pending.get(user_id)
        if existing is not None and not existing.done():
            existing.cancel()
        self._pending[user_id] = asyncio.create_task(
            self._run_after_debounce(user_id)
        )

    async def _run_after_debounce(self, user_id: str) -> None:
        try:
            await asyncio.sleep(self._debounce)
        except asyncio.CancelledError:
            return
        await self._run_now(user_id)

    async def _run_now(self, user_id: str) -> None:
        async with self._lock_for(user_id):
            try:
                report = await self._callable(user_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "T3:curation_scheduler: curation failed for %s: %s",
                    user_id, exc, exc_info=True,
                )
            else:
                # curate returns a status dict; test callables return None.
                # Surface a line only when something actually happened.
                status = report.get("status") if isinstance(report, dict) else None
                if status is not None and status not in _SKIP_STATUSES:
                    logger.info(
                        "T3:curation_scheduler: user=%s status=%s",
                        user_id, status,
                    )
            finally:
                # Drop the pending entry only if it's still ours.
                current = self._pending.get(user_id)
                if current is not None and current.done():
                    self._pending.pop(user_id, None)

    async def flush(self, user_id: str) -> None:
        """Test helper: cancel any pending debounce and run curation now."""
        existing = self._pending.pop(user_id, None)
        if existing is not None and not existing.done():
            existing.cancel()
            try:
                await existing
            except (asyncio.CancelledError, Exception):
                pass
        await self._run_now(user_id)

    async def close(self) -> None:
        """Cancel all pending debounce tasks; wait for in-flight curations."""
        self._closed = True
        tasks = list(self._pending.values())
        self._pending.clear()
        for t in tasks:
            if not t.done():
                t.cancel()
        for t in tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
