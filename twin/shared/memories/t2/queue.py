"""Redis queue for T2 consolidation jobs."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class MemoryJob(BaseModel):
    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    reason: Literal["overflow", "inactivity", "manual"] = "manual"
    snapshot: list[dict] | None = None
    attempts: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MemoryJobQueue:
    QUEUE_KEY = "memory:consolidation:queue"
    PROCESSING_KEY = "memory:consolidation:processing"
    DEAD_LETTER_KEY = "memory:consolidation:dead_letter"
    CHECKPOINT_PREFIX = "memory:consolidation:checkpoint"

    def __init__(self, redis_client):
        self.redis = redis_client

    async def push(self, user_id: str, snapshot: list | None = None, reason: str = "overflow") -> MemoryJob:
        snapshot_dicts = []
        for entry in snapshot or []:
            if hasattr(entry, "model_dump"):
                snapshot_dicts.append(entry.model_dump(mode="json"))
            elif hasattr(entry, "dict"):
                snapshot_dicts.append(entry.dict())
            else:
                snapshot_dicts.append(entry)
        job = MemoryJob(user_id=user_id, reason=reason, snapshot=snapshot_dicts)
        await self.redis.lpush(self.QUEUE_KEY, job.model_dump_json())
        return job

    async def pop(self) -> MemoryJob | None:
        payload = await self.redis.rpop(self.QUEUE_KEY)
        if payload is None:
            return None
        if isinstance(payload, bytes):
            payload = payload.decode()
        try:
            job = MemoryJob.model_validate_json(payload)
        except Exception:
            return None
        await self.redis.hset(self.PROCESSING_KEY, job.job_id, job.model_dump_json())
        return job

    async def checkpoint(self, job_id: str, status: str, data: dict | None = None) -> None:
        await self.redis.set(
            f"{self.CHECKPOINT_PREFIX}:{job_id}",
            json.dumps({"status": status, "data": data or {}}, ensure_ascii=False),
        )

    async def complete(self, job: MemoryJob) -> None:
        await self.redis.hdel(self.PROCESSING_KEY, job.job_id)
        await self.redis.delete(f"{self.CHECKPOINT_PREFIX}:{job.job_id}")

    async def fail(self, job: MemoryJob, error: str, *, max_attempts: int = 3) -> None:
        await self.redis.hdel(self.PROCESSING_KEY, job.job_id)
        job.attempts += 1
        if job.attempts >= max_attempts:
            await self.redis.lpush(self.DEAD_LETTER_KEY, job.model_dump_json())
            await self.checkpoint(job.job_id, "dead_letter", {"error": error})
        else:
            await self.redis.lpush(self.QUEUE_KEY, job.model_dump_json())
            await self.checkpoint(job.job_id, "retry", {"error": error, "attempts": job.attempts})

    async def get_queue_length(self) -> int:
        return await self.redis.llen(self.QUEUE_KEY)

    async def peek_all(self):
        items = await self.redis.lrange(self.QUEUE_KEY, 0, -1)
        result = []
        for item in items:
            if isinstance(item, bytes):
                item = item.decode()
            job = MemoryJob.model_validate_json(item)
            result.append((job.user_id, job.snapshot or []))
        return result
