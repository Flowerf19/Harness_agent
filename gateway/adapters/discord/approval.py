"""Discord approval backend for shared ApprovalGate."""

from __future__ import annotations

from typing import TYPE_CHECKING

from twin.shared.tools.approval_context import ApprovalRequestContext

if TYPE_CHECKING:
    import discord


class DiscordApprovalBackend:
    """Render channel approval through Discord buttons."""

    async def request_channel_approval(
        self,
        context: ApprovalRequestContext,
        command: str,
    ) -> bool:
        from gateway.adapters.discord.views.approve_view import ApproveView

        message = context.native_message
        if message is None or not hasattr(message, "channel"):
            return False

        view = ApproveView(command=command)
        sent_msg = await message.channel.send(
            f"🔐 **Bot muốn chạy lệnh trên host:**\n"
            f"```bash\n{command[:500]}\n```\n"
            f"Cho phép? (Timeout: 30 giây)",
            view=view,
        )

        try:
            return await view.wait_for_decision()
        finally:
            try:
                await sent_msg.delete()
            except Exception:
                pass


def build_discord_approval_context(
    message: "discord.Message",
    *,
    approval_backend: DiscordApprovalBackend | None = None,
) -> ApprovalRequestContext:
    """Build a neutral approval context from a Discord message."""
    channel = message.channel
    guild = message.guild

    channel_name = str(channel)
    if getattr(channel, "name", None):
        channel_name = f"#{channel.name}"
    if guild:
        channel_name = f"{guild.name}/{channel_name}"

    channel_id = str(channel.id)
    return ApprovalRequestContext(
        platform="discord",
        user_id=str(message.author.id),
        conversation_id=channel_id,
        channel_id=channel_id,
        message_id=str(message.id),
        channel_name=channel_name,
        space_id=str(guild.id) if guild else None,
        user_name=message.author.display_name,
        native_message=message,
        approval_backend=approval_backend or DiscordApprovalBackend(),
    )
