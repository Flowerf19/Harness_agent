"""March7 compatibility wrapper for the shared T2 consolidation queue."""
from __future__ import annotations

from twin.shared.memories.t2.queue import MemoryJobQueue


class OverflowQueue(MemoryJobQueue):
    """Deprecated name retained for existing March7 imports."""

    QUEUE_KEY = MemoryJobQueue.QUEUE_KEY
    CHECKPOINT_KEY = "memory:consolidation:checkpoint"

    async def push(self, user_id: str, snapshot: list, reason: str = "overflow") -> None:
        await super().push(user_id=user_id, snapshot=snapshot, reason=reason)

    async def pop(self):
        job = await super().pop()
        if not job:
            return None
        return (job.user_id, job.snapshot or [])

    async def checkpoint(self, user_id: str, status: str, data: dict | None = None) -> None:
        await self.redis.hset(self.CHECKPOINT_KEY, user_id, self._checkpoint_payload(status, data))

    async def get_checkpoint(self, user_id: str):
        import json

        raw = await self.redis.hget(self.CHECKPOINT_KEY, user_id)
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode()
        return json.loads(raw)

    async def clear_checkpoint(self, user_id: str) -> None:
        await self.redis.hdel(self.CHECKPOINT_KEY, user_id)

    async def clear_queue(self) -> int:
        length = await self.get_queue_length()
        if length:
            await self.redis.delete(self.QUEUE_KEY)
        return length

    def _checkpoint_payload(self, status: str, data: dict | None = None) -> str:
        import json

        return json.dumps({"status": status, "data": data or {}}, ensure_ascii=False)
