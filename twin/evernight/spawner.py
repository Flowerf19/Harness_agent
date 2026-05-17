"""Legacy in-process Evernight spawner used by older tests.

Production uses the Redis ``MemoryWorker``. This class remains as a small
compatibility adapter for integration tests and local in-process flows.
"""
from __future__ import annotations

import asyncio
from typing import Any


class EvernightSpawner:
    def __init__(self, evernight_agent: Any, overflow_queue: Any):
        self.agent = evernight_agent
        self.queue = overflow_queue
        self._tasks: set[asyncio.Task] = set()

    def spawn(self) -> asyncio.Task:
        task = asyncio.create_task(self._process_one())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def _process_one(self) -> bool:
        items = await self.queue.peek_all()
        if not items:
            return False
        user_id, snapshot = items[0]
        return bool(await self.agent.consolidate(user_id, snapshot))

    def get_active_task_count(self) -> int:
        return len(self._tasks)

    async def wait_all_complete(self, timeout: float = 5.0) -> None:
        if not self._tasks:
            return
        await asyncio.wait_for(asyncio.gather(*list(self._tasks), return_exceptions=True), timeout=timeout)
