"""
Approval Context - Context variable để truyền Discord channel reference
qua toàn bộ pipeline xử lý mà không cần sửa tất cả các layer.

Khi DiscordGatewayHandler bắt đầu xử lý message, nó set context này.
ApprovalGate đọc context để gửi Discord interaction.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import discord

# Context variable lưu discord.Message hiện tại đang được xử lý
_current_discord_message: ContextVar[discord.Message | None] = ContextVar(
    "current_discord_message", default=None
)


def set_current_message(message: discord.Message) -> None:
    """Set discord.Message hiện tại vào context."""
    _current_discord_message.set(message)


def get_current_message() -> discord.Message | None:
    """Lấy discord.Message hiện tại từ context."""
    return _current_discord_message.get(None)


def clear_current_message() -> None:
    """Xóa context (dùng token reset)."""
    _current_discord_message.set(None)
