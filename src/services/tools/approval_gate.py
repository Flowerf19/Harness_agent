"""
ApprovalGate - Trạm Gác bảo vệ cho các tool nguy hiểm.

Chặn mọi lệnh execute_host_bash trước khi thực thi,
yêu cầu xác nhận từ user qua Discord button UI.

Architecture:
- check_approval() là interface chính
- _request_user_approval() gửi Discord View + đợi user click
"""

from __future__ import annotations

import logging

from src.services.tools.approval_context import get_current_message

logger = logging.getLogger(__name__)


class ApprovalGate:
    """Trạm Gác - chặn và xác nhận execute_host_bash qua Discord UI."""

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
            logger.warning("No Discord message in context, auto-approving")
            return True

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
