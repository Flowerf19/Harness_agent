"""
ApprovalGate - Trạm Gác bảo vệ cho các tool nguy hiểm.

Chặn mọi lệnh trước khi thực thi, yêu cầu xác nhận từ user.
Kiến trúc: Phase 1 auto-approve + log. Phase 2 sẽ có Discord button UI.

Design: Strategy Pattern
- check_approval() là interface chính
- _request_user_approval() là hook cho Discord UI
"""

import logging

logger = logging.getLogger(__name__)


class ApprovalGate:
    """
    Trạm Gác - chặn và xác nhận các tool nguy hiểm.

    Mỗi lần một tool có requires_approval=True được gọi,
    ApprovalGate.check_approval() được gọi TRƯỚC KHI thực thi.

    Phase 1 (hiện tại): auto-approve + log
    Phase 2 (tương lai): Discord message với nút [Approve] [Reject]

    Usage:
        gate = ApprovalGate()
        if await gate.check_approval("execute_host_bash", "rm -rf /"):
            # execute
        else:
            return "Lệnh bị từ chối"
    """

    async def check_approval(self, tool_name: str, command: str) -> bool:
        """
        Kiểm tra xem tool có được phép thực thi không.

        Args:
            tool_name: Tên tool yêu cầu approval
            command: Lệnh hoặc mô tả hành động

        Returns:
            bool: True nếu được phép, False nếu bị từ chối
        """
        logger.warning(f"🔐 APPROVAL REQUESTED: {tool_name} -> {command[:100]}")

        approved = await self._request_user_approval(tool_name, command)

        if approved:
            logger.info(f"✅ APPROVED: {tool_name}")
        else:
            logger.warning(f"❌ REJECTED: {tool_name}")

        return approved

    async def _request_user_approval(self, tool_name: str, command: str) -> bool:
        """
        Yêu cầu user xác nhận qua Discord UI.

        HOOK CHO PHASE 2.
        Hiện tại auto-approve để dev/test.

        Phase 2 sẽ:
        1. Gửi Discord ephemeral message: "Bot muốn chạy: {command}"
        2. Thêm 2 nút: [✅ Approve] [❌ Reject]
        3. Đợi user click (timeout 30s)
        4. Return True nếu Approve, False nếu Reject/Timeout

        Args:
            tool_name: Tên tool
            command: Lệnh cần xác nhận

        Returns:
            bool: True (auto-approve trong Phase 1)
        """
        # Phase 1: auto-approve
        # TODO Phase 2: implement Discord interaction
        return True
