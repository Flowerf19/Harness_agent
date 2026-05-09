"""Inactivity trigger for Evernight consolidation."""
import asyncio
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class InactivityTrigger:
    def __init__(
        self,
        redis_client: Any,
        evernight_agent: Any,
        inactivity_seconds: int = 1800,
        poll_interval: int = 60,
    ):
        self.redis = redis_client
        self.agent = evernight_agent
        self.inactivity_seconds = inactivity_seconds
        self.poll_interval = poll_interval
        self._processed: set = set()
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info(f"InactivityTrigger started (inactivity={self.inactivity_seconds}s, poll={self.poll_interval}s)")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("InactivityTrigger stopped")

    async def _poll_loop(self):
        while self._running:
            try:
                await asyncio.sleep(self.poll_interval)
                await self._scan_inactive_users()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"InactivityTrigger poll error: {e}")

    async def _scan_inactive_users(self):
        try:
            keys = await self.redis.keys("conversation:*:last_active")
            now = time.time()
            for key in keys:
                key_str = key.decode() if isinstance(key, bytes) else key
                user_id = key_str.split(":")[1]
                if user_id in self._processed:
                    continue

                last_active_str = await self.redis.get(key)
                if not last_active_str:
                    continue

                last_active = float(last_active_str)
                if (now - last_active) > self.inactivity_seconds:
                    self._processed.add(user_id)
                    await self._trigger_consolidation(user_id, key)
        except Exception as e:
            logger.error(f"InactivityTrigger scan error: {e}")

    async def _trigger_consolidation(self, user_id: str, key: Any):
        try:
            logger.info(f"InactivityTrigger: user {user_id} inactive, triggering consolidation")

            # Try to get snapshot from March7's T1
            try:
                snapshot_key = f"march7:t1:{user_id}"
                snapshot_data = await self.redis.lrange(snapshot_key, 0, -1)
                if snapshot_data:
                    import json
                    snapshot = [json.loads(s) if isinstance(s, (str, bytes)) else s for s in snapshot_data]
                    await self.agent.consolidate(user_id, snapshot)
            except Exception as e:
                logger.error(f"Failed to get March7 snapshot for {user_id}: {e}")

            # Clear the activity key after consolidation
            await self.redis.delete(key)
            self._processed.discard(user_id)
            logger.info(f"InactivityTrigger: consolidation triggered for {user_id}")
        except Exception as e:
            logger.error(f"InactivityTrigger: consolidation failed for {user_id}: {e}")
