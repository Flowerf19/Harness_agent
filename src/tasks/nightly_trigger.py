"""NightlyTrigger - Scheduled consolidation task."""
import asyncio
import logging
from datetime import datetime, time, timedelta
from typing import TYPE_CHECKING, Optional, Set

if TYPE_CHECKING:
    from src.services.queue.overflow_queue import OverflowQueue
    from src.agents.evernight.spawner import EvernightSpawner

logger = logging.getLogger(__name__)


class NightlyTrigger:
    """
    Scheduled trigger for nightly consolidation.

    SRP: Only handles scheduling and triggering.
    """

    def __init__(
        self,
        overflow_queue: "OverflowQueue",
        evernight_spawner: "EvernightSpawner",
        trigger_hour: int = 2,  # 2 AM default
        trigger_minute: int = 0,
    ):
        """
        Initialize NightlyTrigger.

        Args:
            overflow_queue: Queue to push snapshots to
            evernight_spawner: Spawner to process queued items
            trigger_hour: Hour to trigger (0-23, default 2 AM)
            trigger_minute: Minute to trigger (0-59, default 0)
        """
        self.queue = overflow_queue
        self.spawner = evernight_spawner
        self.trigger_hour = trigger_hour
        self.trigger_minute = trigger_minute
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._processed_users: Set[str] = set()  # Track processed users per cycle

    async def start(self) -> None:
        """Start the scheduled task loop."""
        if self._running:
            logger.warning("⚠️ NightlyTrigger: Already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.debug(f"🕐 NightlyTrigger: Started (trigger at {self.trigger_hour:02d}:{self.trigger_minute:02d})")

    async def stop(self) -> None:
        """Stop the scheduled task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.debug("🛑 NightlyTrigger: Stopped")

    async def _run_loop(self) -> None:
        """Main loop that sleeps until trigger time."""
        while self._running:
            try:
                # Calculate time until next trigger
                now = datetime.now()
                next_trigger = self._get_next_trigger_time(now)
                wait_seconds = (next_trigger - now).total_seconds()

                if wait_seconds > 0:
                    logger.debug(f"💤 NightlyTrigger: Sleeping {wait_seconds/3600:.1f}h until {next_trigger}")
                    await asyncio.sleep(wait_seconds)

                # Check if still running after sleep
                if not self._running:
                    break

                # Trigger consolidation
                logger.debug("🌅 NightlyTrigger: Triggering nightly consolidation")
                await self._scan_and_queue_users()
                await self.spawner.process_queue()

                # Clear processed users for next cycle
                self._processed_users.clear()

            except asyncio.CancelledError:
                logger.debug("🌙 NightlyTrigger: Loop cancelled")
                break
            except Exception as e:
                logger.error(f"❌ NightlyTrigger: Error in loop: {e}", exc_info=True)
                # Wait before retrying to avoid tight error loop
                await asyncio.sleep(60)

    def _get_next_trigger_time(self, now: datetime) -> datetime:
        """
        Calculate next trigger time.

        Args:
            now: Current datetime

        Returns:
            Next trigger datetime
        """
        today_trigger = now.replace(
            hour=self.trigger_hour,
            minute=self.trigger_minute,
            second=0,
            microsecond=0,
        )

        if now < today_trigger:
            return today_trigger
        else:
            # Next day
            return today_trigger + timedelta(days=1)

    async def _scan_and_queue_users(self) -> int:
        """
        Scan for users with T1 data that haven't overflowed.

        This method looks for users who have active T1 sessions
        and queues them for consolidation.

        Returns:
            Number of users queued
        """
        try:
            # Note: This requires access to T1 storage to scan for active users.
            # The actual implementation depends on how T1 storage tracks users.
            # For Redis storage, we can scan keys with pattern "active_memory:*"

            # This is a placeholder that should be connected to the actual
            # T1 storage scanning mechanism when available.
            logger.debug("🔍 NightlyTrigger: Scanning for users with T1 data")

            # For now, return 0 - actual implementation would scan T1 storage
            # and push users with pending data to the queue
            return 0

        except Exception as e:
            logger.error(f"❌ NightlyTrigger: Failed to scan users: {e}")
            return 0

    async def trigger_now(self) -> None:
        """
        Manually trigger consolidation immediately.

        Used for testing or manual intervention.
        """
        logger.debug("⚡ NightlyTrigger: Manual trigger")
        await self._scan_and_queue_users()
        await self.spawner.process_queue()

    def is_running(self) -> bool:
        """Check if the trigger is running."""
        return self._running