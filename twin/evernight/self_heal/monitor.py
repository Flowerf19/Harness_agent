"""Self-heal monitor for Evernight → March7."""
from __future__ import annotations

import asyncio
import logging
import subprocess

import aiohttp

logger = logging.getLogger(__name__)

# Default user ID for self-heal notifications
DEFAULT_NOTIFY_USER_ID = 726302130318868500


class SelfHealMonitor:
    """Polls March7 health endpoint and restarts it on repeated failures."""

    def __init__(
        self,
        march7_url: str = "http://march7:8000",
        interval: int = 30,
        timeout: int = 10,
        failure_threshold: int = 3,
        container_name: str = "march7",
        discord_adapter=None,
        notify_user_id: int = DEFAULT_NOTIFY_USER_ID,
    ):
        self.march7_url = march7_url.rstrip("/")
        self.interval = interval
        self.timeout = timeout
        self.failure_threshold = failure_threshold
        self.container_name = container_name
        self._discord_adapter = discord_adapter
        self._notify_user_id = notify_user_id

        self._failure_count = 0
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self):
        """Start the monitoring loop."""
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("Self-heal monitor started, polling %s every %ds", self.march7_url, self.interval)

    async def stop(self):
        """Stop the monitoring loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Self-heal monitor stopped")

    async def _poll_loop(self):
        while self._running:
            try:
                healthy = await self._check_health()
                if healthy:
                    self._failure_count = 0
                else:
                    self._failure_count += 1
                    logger.warning(
                        "March7 health check failed (%d/%d consecutive failures)",
                        self._failure_count,
                        self.failure_threshold,
                    )
                    if self._failure_count >= self.failure_threshold:
                        await self._restart_march7()
                        self._failure_count = 0
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Self-heal monitor error in poll loop")

            await asyncio.sleep(self.interval)

    async def _check_health(self) -> bool:
        """Check March7 health via A2A agent card endpoint."""
        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{self.march7_url}/.well-known/agent.json") as resp:
                    return resp.status == 200
        except Exception:
            logger.debug("March7 health check unreachable at %s", self.march7_url)
            return False

    async def _restart_march7(self):
        """Restart the March7 container via docker command."""
        logger.warning("Restarting March7 container: %s", self.container_name)
        try:
            result = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    "docker", "restart", self.container_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                ),
                timeout=30,
            )
            stdout, stderr = await result.communicate()
            if result.returncode == 0:
                logger.info("March7 container restarted successfully: %s", stdout.decode().strip())
                await self._notify_restart()
            else:
                logger.error("docker restart failed: %s", stderr.decode().strip())
        except asyncio.TimeoutError:
            logger.error("docker restart timed out")
        except FileNotFoundError:
            logger.error("docker command not found — cannot restart March7")
        except Exception:
            logger.exception("Failed to restart March7 container")

    async def _notify_restart(self):
        """Notify users about the restart via Discord DM."""
        if self._discord_adapter is None:
            logger.info("March7 container restarted (no Discord adapter for notification)")
            return

        try:
            await self._discord_adapter.send_dm(
                user_id=self._notify_user_id,
                content=f"⚠️ **March7 tự khởi động lại:** Container `{self.container_name}` đã được self-heal monitor tự động restart sau {self.failure_threshold} lần health check thất bại.",
            )
            logger.info("Restart notification sent to user %s", self._notify_user_id)
        except Exception:
            logger.exception("Failed to send restart notification")
