"""EvernightSpawner - Spawns and manages Evernight consolidation tasks."""
import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict  # noqa: F401

if TYPE_CHECKING:
    from twin.evernight.agent import EvernightAgent
    from twin.march7.memories.overflow_queue import OverflowQueue

logger = logging.getLogger(__name__)


class EvernightSpawner:
    """
    Spawns and manages Evernight consolidation tasks.

    SRP: Only handles task spawning and tracking.
    """

    def __init__(
        self,
        evernight_agent: "EvernightAgent",
        overflow_queue: "OverflowQueue",
    ):
        """
        Initialize EvernightSpawner.

        Args:
            evernight_agent: EvernightAgent instance for consolidation
            overflow_queue: Queue for checkpoint management
        """
        self.agent = evernight_agent
        self.queue = overflow_queue
        self._active_tasks: Dict[str, asyncio.Task] = {}

    async def spawn_for_user(self, user_id: str, snapshot: list) -> None:
        """
        Spawn Evernight task for a specific user (fire and forget).

        Args:
            user_id: Discord user ID
            snapshot: List of message dicts from T1 memory
        """
        # Don't spawn duplicate tasks for same user
        if user_id in self._active_tasks:
            existing_task = self._active_tasks[user_id]
            if not existing_task.done():
                logger.warning(f"⚠️ EvernightSpawner: Task already running for user {user_id}")
                return

        # Create task
        task = asyncio.create_task(
            self._run_consolidation(user_id, snapshot),
            name=f"evernight_{user_id}",
        )

        # Add done callback for cleanup
        task.add_done_callback(lambda t: self._cleanup_task(user_id))

        self._active_tasks[user_id] = task
        logger.info(f"🚀 EvernightSpawner: Spawned task for user {user_id}")

    async def process_queue(self) -> int:
        """
        Process all items in queue.

        Returns:
            Number of items processed
        """
        processed = 0

        while True:
            item = await self.queue.pop()
            if item is None:
                break

            user_id, snapshot = item
            await self.spawn_for_user(user_id, snapshot)
            processed += 1

        logger.info(f"📦 EvernightSpawner: Spawned {processed} consolidation tasks")
        return processed

    def _cleanup_task(self, user_id: str) -> None:
        """
        Remove completed task from tracking.

        Args:
            user_id: Discord user ID
        """
        if user_id in self._active_tasks:
            del self._active_tasks[user_id]
            logger.debug(f"🧹 EvernightSpawner: Cleaned up task for user {user_id}")

    async def _run_consolidation(self, user_id: str, snapshot: list) -> bool:
        """
        Run consolidation with error handling and checkpoint.

        Args:
            user_id: Discord user ID
            snapshot: List of message dicts from T1 memory

        Returns:
            True if successful, False otherwise
        """
        try:
            # Set checkpoint to processing
            await self.queue.checkpoint(user_id, "processing", {
                "snapshot_size": len(snapshot),
            })

            # Run consolidation
            success = await self.agent.consolidate(user_id, snapshot)

            if success:
                # Clear checkpoint on success
                await self.queue.clear_checkpoint(user_id)
                logger.info(f"✅ EvernightSpawner: Consolidation complete for user {user_id}")
            else:
                # Set checkpoint to failed
                await self.queue.checkpoint(user_id, "failed", {
                    "error": "Agent returned False",
                    "snapshot_size": len(snapshot),
                })
                logger.warning(f"⚠️ EvernightSpawner: Consolidation failed for user {user_id}")

            return success

        except Exception as e:
            # Set checkpoint to error
            await self.queue.checkpoint(user_id, "error", {
                "error": str(e),
                "error_type": type(e).__name__,
            })
            logger.error(f"❌ EvernightSpawner: Error for user {user_id}: {e}", exc_info=True)
            return False

    async def retry_failed(self) -> int:
        """
        Retry failed consolidations from checkpoints.

        Returns:
            Number of retries attempted
        """
        # This would require scanning checkpoints for failed/error status
        # and re-queueing them. Implementation depends on how we track
        # failed checkpoints across all users.
        logger.info("🔄 EvernightSpawner: Retry mechanism not yet implemented")
        return 0

    def get_active_task_count(self) -> int:
        """Get number of currently active tasks."""
        return len([t for t in self._active_tasks.values() if not t.done()])

    async def wait_all_complete(self, timeout: float = 300.0) -> None:
        """
        Wait for all active tasks to complete.

        Args:
            timeout: Maximum time to wait in seconds
        """
        active_tasks = [t for t in self._active_tasks.values() if not t.done()]

        if not active_tasks:
            return

        logger.info(f"⏳ EvernightSpawner: Waiting for {len(active_tasks)} tasks to complete")

        try:
            await asyncio.wait(active_tasks, timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("⚠️ EvernightSpawner: Timeout waiting for tasks")