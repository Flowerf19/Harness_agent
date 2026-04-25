"""OverflowQueue - Redis-based queue for T1 overflow snapshots."""
import json
import logging
from typing import List, Optional, Tuple

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class OverflowQueue:
    """
    Redis-based queue for T1 overflow snapshots.

    SRP: Only handles queue operations (push/pop/checkpoint).

    Redis Structure:
    - QUEUE_KEY: LIST for FIFO queue (LPUSH/RPOP)
    - CHECKPOINT_KEY: HASH for recovery state (user_id -> checkpoint_data)
    """

    QUEUE_KEY = "evernight:overflow_queue"
    CHECKPOINT_KEY = "evernight:checkpoint"

    def __init__(self, redis_client: redis.Redis):
        """
        Initialize OverflowQueue.

        Args:
            redis_client: Redis client instance (shared with T1 storage)
        """
        self.redis = redis_client

    async def push(self, user_id: str, snapshot: List[dict]) -> None:
        """
        Push snapshot to queue for processing.

        Args:
            user_id: Discord user ID
            snapshot: List of message dicts from T1 memory
        """
        try:
            payload = json.dumps({
                "user_id": user_id,
                "snapshot": snapshot,
            })
            await self.redis.lpush(self.QUEUE_KEY, payload)
            logger.info(f"📤 OverflowQueue: Pushed snapshot for user {user_id} ({len(snapshot)} messages)")
        except Exception as e:
            logger.error(f"❌ OverflowQueue: Failed to push for user {user_id}: {e}")
            raise

    async def pop(self) -> Optional[Tuple[str, List[dict]]]:
        """
        Pop next item from queue.

        Returns:
            Tuple of (user_id, snapshot) or None if queue empty
        """
        try:
            payload = await self.redis.rpop(self.QUEUE_KEY)
            if payload is None:
                return None

            data = json.loads(payload)
            user_id = data["user_id"]
            snapshot = data["snapshot"]
            logger.debug(f"📥 OverflowQueue: Popped snapshot for user {user_id}")
            return (user_id, snapshot)

        except json.JSONDecodeError as e:
            logger.error(f"❌ OverflowQueue: Failed to decode payload: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ OverflowQueue: Failed to pop: {e}")
            raise

    async def checkpoint(self, user_id: str, status: str, data: Optional[dict] = None) -> None:
        """
        Save checkpoint for error recovery.

        Args:
            user_id: Discord user ID
            status: Current status (e.g., "processing", "completed", "failed")
            data: Optional additional checkpoint data
        """
        try:
            checkpoint_data = {
                "status": status,
                "data": data or {},
            }
            await self.redis.hset(
                self.CHECKPOINT_KEY,
                user_id,
                json.dumps(checkpoint_data),
            )
            logger.debug(f"💾 OverflowQueue: Saved checkpoint for user {user_id} (status={status})")
        except Exception as e:
            logger.error(f"❌ OverflowQueue: Failed to save checkpoint: {e}")
            # Don't raise - checkpoint failure shouldn't break processing

    async def get_checkpoint(self, user_id: str) -> Optional[dict]:
        """
        Get checkpoint for a user.

        Args:
            user_id: Discord user ID

        Returns:
            Checkpoint dict or None if not found
        """
        try:
            data = await self.redis.hget(self.CHECKPOINT_KEY, user_id)
            if data is None:
                return None
            return json.loads(data)
        except json.JSONDecodeError as e:
            logger.error(f"❌ OverflowQueue: Failed to decode checkpoint: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ OverflowQueue: Failed to get checkpoint: {e}")
            raise

    async def clear_checkpoint(self, user_id: str) -> None:
        """
        Clear checkpoint after successful completion.

        Args:
            user_id: Discord user ID
        """
        try:
            await self.redis.hdel(self.CHECKPOINT_KEY, user_id)
            logger.debug(f"🗑️ OverflowQueue: Cleared checkpoint for user {user_id}")
        except Exception as e:
            logger.error(f"❌ OverflowQueue: Failed to clear checkpoint: {e}")
            # Don't raise - checkpoint cleanup failure shouldn't break processing

    async def get_queue_length(self) -> int:
        """
        Get number of pending items in queue.

        Returns:
            Number of items in queue
        """
        try:
            length = await self.redis.llen(self.QUEUE_KEY)
            return length
        except Exception as e:
            logger.error(f"❌ OverflowQueue: Failed to get queue length: {e}")
            raise

    async def peek_all(self) -> List[Tuple[str, List[dict]]]:
        """
        Peek at all items in queue without removing them.

        Used for debugging/monitoring.

        Returns:
            List of (user_id, snapshot) tuples
        """
        try:
            items = await self.redis.lrange(self.QUEUE_KEY, 0, -1)
            result = []
            for item in items:
                try:
                    data = json.loads(item)
                    result.append((data["user_id"], data["snapshot"]))
                except json.JSONDecodeError:
                    continue
            return result
        except Exception as e:
            logger.error(f"❌ OverflowQueue: Failed to peek queue: {e}")
            raise

    async def clear_queue(self) -> int:
        """
        Clear all items from queue.

        Returns:
            Number of items cleared
        """
        try:
            length = await self.get_queue_length()
            if length > 0:
                await self.redis.delete(self.QUEUE_KEY)
            logger.info(f"🗑️ OverflowQueue: Cleared {length} items from queue")
            return length
        except Exception as e:
            logger.error(f"❌ OverflowQueue: Failed to clear queue: {e}")
            raise