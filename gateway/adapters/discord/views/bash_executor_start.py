"""
BashExecutorStartView - Discord View khi host tool không kết nối được.

Hiện ra khi execute_host_bash fail vì không kết nối được đến bash executor.
Có 2 nút: [Thử lại] retry lệnh, [Hủy] đóng.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from gateway.adapters.discord.handler import DiscordGatewayHandler

logger = logging.getLogger(__name__)


class BashExecutorStartView(discord.ui.View):
    def __init__(
        self,
        handler: DiscordGatewayHandler,
        raw_message: discord.Message,
        user_id: str,
        content: str,
    ):
        super().__init__(timeout=30)
        self.handler = handler
        self.raw_message = raw_message
        self.user_id = user_id
        self.content = content

    @discord.ui.button(label="🔄 Thử lại", style=discord.ButtonStyle.green)
    async def retry_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.disable_all_items()
        await interaction.response.edit_message(
            content="⏳ Đang thử lại lệnh...",
            view=self,
        )

        await asyncio.sleep(2)

        try:
            await self.handler.retry_process_message(
                raw_message=self.raw_message,
                user_id=self.user_id,
                content=self.content,
            )
        except Exception:
            logger.exception("Retry process_message failed")

    @discord.ui.button(label="❌ Hủy", style=discord.ButtonStyle.gray)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.disable_all_items()
        await interaction.response.edit_message(
            content="❌ Đã hủy.",
            view=self,
        )

    async def on_timeout(self):
        self.disable_all_items()
        try:
            await self.raw_message.edit(
                content="⏰ Hết thời gian chờ. Gửi lại lệnh nếu bạn muốn thử lại.",
                view=self,
            )
        except discord.HTTPException:
            pass
