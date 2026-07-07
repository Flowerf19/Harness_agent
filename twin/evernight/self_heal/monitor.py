"""Self-heal monitor for Evernight → March7."""
from __future__ import annotations

import asyncio
import logging
import os
from abc import ABC, abstractmethod

import aiohttp

logger = logging.getLogger(__name__)

# Default user ID for self-heal notifications
DEFAULT_NOTIFY_USER_ID = 726302130318868500


class RecoveryExecutor(ABC):
    @abstractmethod
    async def restart_container(self, container_name: str) -> tuple[bool, str]:
        """Restart a container and return (success, detail)."""


class GatewayRecoveryExecutor(RecoveryExecutor):
    """Restart containers via the System Gateway policy-gated restart path.

    Preferred over DockerCommandRecoveryExecutor when SYSTEM_GATEWAY_URL is
    configured.
    """

    def __init__(self, gateway_monitor):
        self.gateway_monitor = gateway_monitor

    async def restart_container(self, container_name: str) -> tuple[bool, str]:
        if self.gateway_monitor is None:
            return False, "GatewayMonitor not available"

        # Mint an approval token for container.restart
        approval_id = None
        client = getattr(self.gateway_monitor, "_client", None)
        if client is not None:
            secret = getattr(client, "shared_secret", None)
            if secret:
                from twin.shared.system_gateway import mint_approval_token

                actor = getattr(client, "actor", "evernight")
                approval_id = mint_approval_token(
                    secret=secret, action="container.restart", actor=actor
                )

        return await self.gateway_monitor.request_container_restart(
            container_name, approval_id=approval_id
        )


class DockerCommandRecoveryExecutor(RecoveryExecutor):
    async def restart_container(self, container_name: str) -> tuple[bool, str]:
        try:
            process = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    "docker", "restart", container_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                ),
                timeout=30,
            )
            stdout, stderr = await process.communicate()
            if process.returncode == 0:
                return True, stdout.decode().strip()
            return False, stderr.decode().strip()
        except asyncio.TimeoutError:
            return False, "docker restart timed out"
        except FileNotFoundError:
            return False, "docker command not found"
        except Exception as e:
            return False, str(e)


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
        recovery_executor: RecoveryExecutor | None = None,
        gateway_monitor=None,
    ):
        self.march7_url = march7_url.rstrip("/")
        self.interval = interval
        self.timeout = timeout
        self.failure_threshold = failure_threshold
        self.container_name = container_name
        self._discord_adapter = discord_adapter
        self._notify_user_id = notify_user_id
        self._gateway_monitor = gateway_monitor

        # Prefer GatewayRecoveryExecutor when SYSTEM_GATEWAY_URL is set
        if recovery_executor is not None:
            self._recovery_executor = recovery_executor
        elif gateway_monitor is not None or os.getenv("SYSTEM_GATEWAY_URL"):
            self._recovery_executor = GatewayRecoveryExecutor(
                gateway_monitor=gateway_monitor
            )
        else:
            self._recovery_executor = DockerCommandRecoveryExecutor()

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
        success, detail = await self._recovery_executor.restart_container(self.container_name)
        if success:
            logger.info("March7 container restarted successfully: %s", detail)
            await self._notify_restart()
        else:
            logger.error("March7 restart failed: %s", detail)

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
