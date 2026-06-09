"""Inactivity trigger — periodic scanner that drives SummaryPolicy.

Each agent (March7 and Evernight) runs its own instance against its own
``SummaryStateRepository`` so the unified summary flow fires even when no
new message arrives (idle channel / quiet user 1-1 chat).

Design rationale: ``SummaryPolicy.evaluate`` already inspects all three
trigger conditions (token / message_count / idle). This trigger is just a
periodic poller — for every active scope, ask the policy to evaluate.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class InactivityTrigger:
    def __init__(
        self,
        state_repo: Any,
        summary_policy: Any,
        scopes: tuple[str, ...] = ("user", "channel"),
        poll_interval: int = 60,
    ):
        self.state_repo = state_repo
        self.summary_policy = summary_policy
        self.scopes = scopes
        self.poll_interval = poll_interval
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info(
            "InactivityTrigger started (poll=%ss, scopes=%s)",
            self.poll_interval,
            self.scopes,
        )

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("InactivityTrigger stopped")

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self.poll_interval)
                await self.scan()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("InactivityTrigger poll error")

    async def scan(self) -> None:
        """Iterate active scope_ids and ask SummaryPolicy to re-evaluate."""
        for scope in self.scopes:
            try:
                scope_ids = await self.state_repo.list_active(scope)
            except Exception:
                logger.exception(
                    "InactivityTrigger: list_active failed scope=%s", scope
                )
                continue

            for scope_id in scope_ids:
                try:
                    await self.summary_policy.evaluate(scope, scope_id)
                except Exception:
                    logger.exception(
                        "InactivityTrigger: evaluate failed %s:%s", scope, scope_id
                    )
