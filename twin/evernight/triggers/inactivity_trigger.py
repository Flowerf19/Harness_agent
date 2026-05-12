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
        consolidation_runner: Any,
        inactivity_seconds: int = 1800,
        poll_interval: int = 60,
    ):
        self.redis = redis_client
        self.runner = consolidation_runner
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

            result = await self.runner.run_for_user(user_id, reason="inactivity")
            if result.success:
                await self.redis.delete(key)
                logger.info(
                    "InactivityTrigger: consolidation complete user=%s snapshot=%s cleared=%s",
                    user_id,
                    result.snapshot_count,
                    result.cleared,
                )
            else:
                logger.warning(
                    "InactivityTrigger: consolidation failed user=%s error=%s",
                    user_id,
                    result.error,
                )
        except Exception as e:
            logger.error(f"InactivityTrigger: consolidation failed for {user_id}: {e}")
        finally:
            self._processed.discard(user_id)
