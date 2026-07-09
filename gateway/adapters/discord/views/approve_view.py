"""
ApproveView - Discord View yêu cầu user approve trước khi chạy lệnh host.

Hiện ra khi ApprovalGate cần xác nhận cho một thao tác có side effect.
Có 2 nút: [Approve] cho phép chạy, [Reject] từ chối. Timeout 30s.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

APPROVAL_TIMEOUT = 30


class ApproveView(discord.ui.View):
    def __init__(self, command: str, timeout: int = APPROVAL_TIMEOUT, context_label: str = ""):
        super().__init__(timeout=timeout)
        self.command = command
        self._timeout = timeout
        self._context_label = context_label
        self._result: asyncio.Event = asyncio.Event()
        self._approved: bool = False

    def _disable_all(self):
        for child in self.children:
            child.disabled = True

    async def _edit_interaction_message(
        self,
        interaction: discord.Interaction,
        content: str,
    ) -> None:
        try:
            await interaction.response.edit_message(content=content, view=self)
        except discord.NotFound:
            logger.warning("Approval message disappeared before it could be updated")
        except discord.HTTPException as exc:
            logger.warning("Failed to update approval message: %s", exc)

    @discord.ui.button(label="✅ Approve", style=discord.ButtonStyle.green)
    async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self._approved = True
        self._result.set()
        self._disable_all()
        await self._edit_interaction_message(
            interaction,
            f"✅ **Đã approve:** `{self.command[:80]}`\nĐang thực thi...",
        )

    @discord.ui.button(label="❌ Reject", style=discord.ButtonStyle.red)
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self._approved = False
        self._result.set()
        self._disable_all()
        await self._edit_interaction_message(
            interaction,
            f"❌ **Đã từ chối:** `{self.command[:80]}`",
        )

    async def wait_for_decision(self) -> bool:
        try:
            await asyncio.wait_for(self._result.wait(), timeout=self._timeout)
            return self._approved
        except asyncio.TimeoutError:
            self._disable_all()
            return False

    async def on_timeout(self):
        self._disable_all()
