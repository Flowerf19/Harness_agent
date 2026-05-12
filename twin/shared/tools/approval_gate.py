"""
ApprovalGate - Trạm Gác bảo vệ cho các tool nguy hiểm.

Chặn mọi lệnh execute_host_bash trước khi thực thi,
yêu cầu xác nhận từ user qua Discord button UI.

Architecture:
- check_approval() là interface chính
- _request_user_approval() gửi Discord View + đợi user click
- Ưu tiên gửi DM qua Evernight bot, fallback về channel nếu không available
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Optional

from twin.shared.tools.approval_context import get_current_message

if TYPE_CHECKING:
    from twin.shared.tools.dm_client import DMClient

logger = logging.getLogger(__name__)


class ApprovalGate:
    """Trạm Gác - chặn và xác nhận execute_host_bash qua Discord UI."""

    def __init__(self, dm_client: Optional["DMClient"] = None):
        """
        Initialize ApprovalGate.

        Args:
            dm_client: Client để gửi DM qua Evernight bot.
                       Nếu None, sẽ dùng channel message (fallback).
        """
        self.dm_client = dm_client

    async def check_approval(self, tool_name: str, command: str) -> bool:
        logger.warning(f"🔐 APPROVAL REQUESTED: {tool_name} -> {command[:100]}")

        approved = await self._request_user_approval(tool_name, command)

        if approved:
            logger.info(f"✅ APPROVED: {tool_name}")
        else:
            logger.warning(f"❌ REJECTED: {tool_name}")

        return approved

    async def _request_user_approval(self, tool_name: str, command: str) -> bool:
        msg = get_current_message()
        if msg is None:
            return self._handle_missing_context()

        # Try DM via Evernight first
        if self.dm_client:
            try:
                from twin.shared.tools.dm_client import DEFAULT_USER_ID
                dm_approved = await self.dm_client.request_approval(
                    command=command,
                    original_message=msg,
                    user_id=DEFAULT_USER_ID,
                )
                return dm_approved
            except Exception:
                logger.warning("DM approval failed, falling back to channel approval")
                # Fall through to channel-based approval

        # Fallback: channel-based approval (original behavior)
        return await self._request_channel_approval(command)

    async def _request_channel_approval(self, command: str) -> bool:
        """Fallback: send approval request to the original channel."""
        msg = get_current_message()
        if msg is None:
            return self._handle_missing_context()

        from gateway.adapters.discord.views.approve_view import ApproveView

        view = ApproveView(command=command)

        sent_msg = await msg.channel.send(
            f"🔐 **Bot muốn chạy lệnh trên host:**\n"
            f"```bash\n{command[:500]}\n```\n"
            f"Cho phép? (Timeout: 30 giây)",
            view=view,
        )

        try:
            result = await view.wait_for_decision()
            return result
        finally:
            try:
                await sent_msg.delete()
            except Exception:
                pass

    def _handle_missing_context(self) -> bool:
        auto_approve = os.getenv(
            "APPROVAL_AUTO_APPROVE_WITHOUT_CONTEXT",
            "false",
        ).lower() in ("1", "true", "yes")
        if auto_approve:
            logger.warning("No Discord message in context, auto-approving by explicit dev config")
            return True

        logger.warning("No Discord message in context, rejecting approval request")
        return False
