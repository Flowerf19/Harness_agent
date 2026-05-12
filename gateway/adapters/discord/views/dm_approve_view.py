"""
DMApproveView — Discord View gửi qua DM để user approve lệnh host.

Thin wrapper around ApproveView with longer timeout (60s) and DM-specific label.
"""

from __future__ import annotations

from gateway.adapters.discord.views.approve_view import ApproveView

DM_APPROVAL_TIMEOUT = 60


class DMApproveView(ApproveView):
    """Approval View sent via DM from Evernight bot."""

    def __init__(self, command: str):
        super().__init__(command, timeout=DM_APPROVAL_TIMEOUT, context_label="!9 muốn chạy lệnh trên host:")
