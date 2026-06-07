"""ApprovalGate - guard dangerous tools behind user approval.

Shared approval code is platform-neutral. Native UI such as Discord buttons is
provided by the gateway adapter through an ApprovalBackend.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Optional

from twin.shared.tools.approval_context import (
    ApprovalBackend,
    ApprovalRequestContext,
    get_current_approval_context,
)

if TYPE_CHECKING:
    from twin.shared.tools.dm_client import DMClient

logger = logging.getLogger(__name__)


class ApprovalGate:
    """Guard dangerous tools behind a platform approval capability."""

    def __init__(
        self,
        dm_client: Optional["DMClient"] = None,
        channel_approval_backend: ApprovalBackend | None = None,
    ):
        """
        Initialize ApprovalGate.

        Args:
            dm_client: Optional client for owner/private approval.
            channel_approval_backend: Optional fallback backend. Platform
                adapters usually provide this on the current context.
        """
        self.dm_client = dm_client
        self.channel_approval_backend = channel_approval_backend

    async def check_approval(self, tool_name: str, command: str) -> bool:
        logger.warning(f"🔐 APPROVAL REQUESTED: {tool_name} -> {command[:100]}")

        approved = await self._request_user_approval(tool_name, command)

        if approved:
            logger.info(f"✅ APPROVED: {tool_name}")
        else:
            logger.warning(f"❌ REJECTED: {tool_name}")

        return approved

    async def _request_user_approval(self, tool_name: str, command: str) -> bool:
        context = get_current_approval_context()
        if context is None:
            return self._handle_missing_context()

        # Try DM/private approval first if configured.
        if self.dm_client:
            try:
                dm_approved = await self.dm_client.request_approval(
                    command=command,
                    context=context,
                )
                return dm_approved
            except Exception:
                logger.warning("DM approval failed, falling back to channel approval")

        return await self._request_channel_approval(context, command)

    async def _request_channel_approval(
        self,
        context: ApprovalRequestContext,
        command: str,
    ) -> bool:
        """Fallback: ask approval through the platform channel backend."""
        backend = context.approval_backend or self.channel_approval_backend
        if backend is None:
            return self._handle_missing_backend(context)

        return await backend.request_channel_approval(context, command)

    def _handle_missing_context(self) -> bool:
        return self._handle_missing_approval_surface(
            "No approval context, auto-approving by explicit dev config",
            "No approval context, rejecting approval request",
        )

    def _handle_missing_backend(self, context: ApprovalRequestContext) -> bool:
        label = f"{context.platform}:{context.conversation_id or context.channel_id or 'unknown'}"
        return self._handle_missing_approval_surface(
            f"No approval backend for {label}, auto-approving by explicit dev config",
            f"No approval backend for {label}, rejecting approval request",
        )

    def _handle_missing_approval_surface(
        self,
        auto_approve_log: str,
        reject_log: str,
    ) -> bool:
        auto_approve = os.getenv(
            "APPROVAL_AUTO_APPROVE_WITHOUT_CONTEXT",
            "false",
        ).lower() in ("1", "true", "yes")
        if auto_approve:
            logger.warning(auto_approve_log)
            return True

        logger.warning(reject_log)
        return False
