"""Evernight worker for queued memory consolidation jobs."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from twin.shared.memories.t2.queue import MemoryJobQueue

logger = logging.getLogger(__name__)


class MemoryWorker:
    def __init__(
        self,
        queue: MemoryJobQueue,
        evernight_agent: Any,
        march7_memory: Any,
        *,
        poll_interval: float = 2.0,
        max_attempts: int = 3,
    ):
        self.queue = queue
        self.agent = evernight_agent
        self.march7_memory = march7_memory
        self.poll_interval = poll_interval
        self.max_attempts = max_attempts
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        while self._running:
            job = await self.queue.pop()
            if not job:
                await asyncio.sleep(self.poll_interval)
                continue
            try:
                await self.process_once(job)
            except Exception:
                logger.exception("MemoryWorker: job failed job_id=%s user=%s", job.job_id, job.user_id)

    async def process_once(self, job=None) -> bool:
        job = job or await self.queue.pop()
        if not job:
            return False
        try:
            snapshot = job.snapshot
            if snapshot is None:
                snapshot = await self.march7_memory.get_snapshot(job.user_id)
            await self.queue.checkpoint(job.job_id, "processing", {"snapshot_size": len(snapshot)})
            success = await self.agent.consolidate(job.user_id, snapshot, reason=job.reason)
            if not success:
                raise RuntimeError("consolidation failed")
            await self.queue.complete(job)
            return True
        except Exception as e:
            await self.queue.fail(job, str(e), max_attempts=self.max_attempts)
            return False
