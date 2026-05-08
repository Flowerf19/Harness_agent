"""
ApproveView - Discord View yêu cầu user approve trước khi chạy lệnh host.

Hiện ra khi ApprovalGate cần xác nhận cho execute_host_bash.
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
    def __init__(self, command: str):
        super().__init__(timeout=APPROVAL_TIMEOUT)
        self.command = command
        self._result: asyncio.Event = asyncio.Event()
        self._approved: bool = False

    @discord.ui.button(label="✅ Approve", style=discord.ButtonStyle.green)
    async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self._approved = True
        self._result.set()
        self.disable_all_items()
        await interaction.response.edit_message(
            content=f"✅ **Đã approve:** `{self.command[:80]}`\nĐang thực thi...",
            view=self,
        )

    @discord.ui.button(label="❌ Reject", style=discord.ButtonStyle.red)
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self._approved = False
        self._result.set()
        self.disable_all_items()
        await interaction.response.edit_message(
            content=f"❌ **Đã từ chối:** `{self.command[:80]}`",
            view=self,
        )

    async def wait_for_decision(self) -> bool:
        try:
            await asyncio.wait_for(self._result.wait(), timeout=APPROVAL_TIMEOUT)
            return self._approved
        except asyncio.TimeoutError:
            self.disable_all_items()
            return False

    async def on_timeout(self):
        self.disable_all_items()
