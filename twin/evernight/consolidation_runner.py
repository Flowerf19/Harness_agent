"""Evernight-side orchestration for March7 memory consolidation."""
from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from twin.shared.a2a.client import A2AClient

logger = logging.getLogger(__name__)


@dataclass
class ConsolidationRunResult:
    success: bool
    user_id: str
    snapshot_count: int = 0
    cleared: bool = False
    reason: str = ""
    error: str | None = None


class March7MemoryClient:
    """A2A client for March7 memory boundary operations."""

    def __init__(self, march7_url: str, timeout: float = 120.0):
        self._client = A2AClient(base_url=march7_url, timeout=timeout)

    async def get_snapshot(self, user_id: str) -> list[dict]:
        data = await self._client.send_data_task(
            skill="get_snapshot",
            session_id=user_id,
        )
        snapshot = data.get("snapshot", [])
        return snapshot if isinstance(snapshot, list) else []

    async def clear_session(self, user_id: str) -> bool:
        data = await self._client.send_data_task(
            skill="clear_session",
            session_id=user_id,
        )
        return bool(data.get("success"))

    async def close(self):
        await self._client.close()


class ConsolidationRunner:
    """Runs the full March7 -> Evernight -> March7 memory loop."""

    def __init__(
        self,
        evernight_agent: Any,
        march7_memory: March7MemoryClient,
        *,
        clear_after_success: bool = True,
    ):
        self.agent = evernight_agent
        self.march7_memory = march7_memory
        self.clear_after_success = clear_after_success
        self._active_users: set[str] = set()

    async def run_for_user(
        self,
        user_id: str,
        *,
        reason: str = "manual",
    ) -> ConsolidationRunResult:
        if user_id in self._active_users:
            return ConsolidationRunResult(
                success=False,
                user_id=user_id,
                reason=reason,
                error="consolidation already running for user",
            )

        self._active_users.add(user_id)
        try:
            logger.info("ConsolidationRunner: fetching snapshot user=%s reason=%s", user_id, reason)
            snapshot = await self.march7_memory.get_snapshot(user_id)
            if not snapshot:
                return ConsolidationRunResult(
                    success=True,
                    user_id=user_id,
                    snapshot_count=0,
                    reason=reason,
                )

            success = await self.agent.consolidate(user_id, snapshot)
            if not success:
                return ConsolidationRunResult(
                    success=False,
                    user_id=user_id,
                    snapshot_count=len(snapshot),
                    reason=reason,
                    error="consolidation failed",
                )

            cleared = False
            if self.clear_after_success:
                cleared = await self.march7_memory.clear_session(user_id)
                if not cleared:
                    logger.warning("ConsolidationRunner: March7 clear_session failed user=%s", user_id)

            return ConsolidationRunResult(
                success=True,
                user_id=user_id,
                snapshot_count=len(snapshot),
                cleared=cleared,
                reason=reason,
            )
        except Exception as e:
            logger.exception("ConsolidationRunner failed for user=%s", user_id)
            return ConsolidationRunResult(
                success=False,
                user_id=user_id,
                reason=reason,
                error=str(e),
            )
        finally:
            self._active_users.discard(user_id)

    async def close(self):
        await self.march7_memory.close()
