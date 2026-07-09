"""Evernight Discord DM and approval HTTP routes."""

import logging

from aiohttp import web

DEFAULT_OWNER_USER_ID = "726302130318868500"

logger = logging.getLogger(__name__)


def _discord_module():
    try:
        import discord
    except ModuleNotFoundError:
        return None
    return discord


class EvernightDMRoutes:
    def __init__(
        self,
        discord_bot=None,
        owner_user_id: str | int = DEFAULT_OWNER_USER_ID,
    ):
        self.discord_bot = discord_bot
        self.owner_user_id = str(owner_user_id)

    async def handle_dm(self, request: web.Request) -> web.Response:
        """Handle general DM request from March7 container."""
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"success": False, "error": "Invalid JSON"}, status=400)

        user_id = body.get("user_id")
        content = body.get("content", "")
        msg_type = body.get("type", "message")

        if str(user_id) != self.owner_user_id:
            logger.warning("DM rejected for non-owner user_id=%s", user_id)
            return web.json_response(
                {"success": False, "error": "Access denied: owner only"},
                status=403,
            )

        if not user_id:
            return web.json_response(
                {"success": False, "error": "Missing user_id"},
                status=400,
            )

        if not self.discord_bot:
            logger.warning("Discord bot not available, cannot send DM")
            return web.json_response(
                {"success": False, "error": "Discord bot not available"},
                status=503,
            )

        if not self.discord_bot.is_ready():
            logger.warning("Discord bot not ready, cannot send DM")
            return web.json_response(
                {"success": False, "error": "Discord bot not ready"},
                status=503,
            )

        try:
            user = await self.discord_bot.fetch_user(user_id)
        except Exception as e:
            logger.exception("Failed to fetch user %s", user_id)
            return web.json_response(
                {"success": False, "error": f"Cannot fetch user: {e}"},
                status=500,
            )

        if msg_type == "approval":
            return await self._handle_approval_type_dm(user, body)
        return await self._handle_message_type_dm(user, content)

    async def _handle_message_type_dm(self, user, content: str) -> web.Response:
        try:
            await user.send(content)
            return web.json_response({"success": True})
        except Exception as e:
            logger.exception("Error sending DM to user %s", user.id)
            return web.json_response({"success": False, "error": str(e)}, status=500)

    async def _handle_approval_type_dm(self, user, body: dict) -> web.Response:
        command = body.get("command", "")
        channel_id = body.get("channel_id")
        message_id = body.get("message_id")
        channel_name = body.get("channel_name", "unknown")

        if not command:
            return web.json_response(
                {"success": False, "error": "Missing command for approval"},
                status=400,
            )

        try:
            from gateway.adapters.discord.views.dm_approve_view import (
                DM_APPROVAL_TIMEOUT,
                DMApproveView,
            )

            view = DMApproveView(command=command)
            dm_content = (
                f"🔐 **Bé Bảy muốn chạy lệnh trên host:**\n"
                f"```bash\n{command[:500]}\n```\n"
                f"📍 Kênh gốc: {channel_name}\n"
                f"Cho phép? (Timeout: {DM_APPROVAL_TIMEOUT} giây)"
            )
            sent_msg = await user.send(dm_content, view=view)
            approved = await view.wait_for_decision()

            try:
                await sent_msg.delete()
            except Exception:
                pass

            if channel_id:
                await self._notify_original_channel(
                    channel_id, message_id, command, approved
                )

            return web.json_response({"approved": approved})

        except Exception as e:
            logger.exception("Error in approval DM handler")
            return web.json_response({"success": False, "error": str(e)}, status=500)

    async def handle_approval_dm(self, request: web.Request) -> web.Response:
        """Deprecated compatibility route for approval DM requests."""
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        user_id = body.get("user_id")
        command = body.get("command", "")
        channel_id = body.get("channel_id")
        message_id = body.get("message_id")
        channel_name = body.get("channel_name", "unknown")

        if not user_id or not command:
            return web.json_response({"error": "Missing user_id or command"}, status=400)

        if not self.discord_bot:
            logger.warning("Discord bot not available, cannot send approval DM")
            return web.json_response({"error": "Discord bot not available"}, status=503)

        if not self.discord_bot.is_ready():
            logger.warning("Discord bot not ready, cannot send approval DM")
            return web.json_response({"error": "Discord bot not ready"}, status=503)

        try:
            from gateway.adapters.discord.views.dm_approve_view import (
                DM_APPROVAL_TIMEOUT,
                DMApproveView,
            )

            user = await self.discord_bot.fetch_user(user_id)
            view = DMApproveView(command=command)

            dm_content = (
                f"🔐 **Bé Bảy muốn chạy lệnh trên host:**\n"
                f"```bash\n{command[:500]}\n```\n"
                f"📍 Kênh gốc: {channel_name}\n"
                f"Cho phép? (Timeout: {DM_APPROVAL_TIMEOUT} giây)"
            )
            sent_msg = await user.send(dm_content, view=view)
            approved = await view.wait_for_decision()

            try:
                await sent_msg.delete()
            except Exception:
                pass

            if channel_id:
                await self._notify_original_channel(channel_id, message_id, command, approved)

            return web.json_response({"approved": approved})

        except Exception as e:
            logger.exception("Error in approval_dm handler")
            return web.json_response({"error": str(e)}, status=500)

    async def _notify_original_channel(
        self,
        channel_id: int,
        message_id: int | None,
        command: str,
        approved: bool,
    ):
        """Send approval result back to the original channel."""
        del message_id
        if not self.discord_bot or not self.discord_bot.is_ready():
            return

        try:
            channel = self.discord_bot.get_channel(channel_id)
            if channel is None:
                channel = await self.discord_bot.fetch_channel(channel_id)

            if approved:
                content = f"🔐 **Lệnh đã được approve:**\n`{command[:200]}`"
            else:
                content = f"🔐 **Lệnh đã bị từ chối:**\n`{command[:200]}`"

            await channel.send(content)
        except Exception as exc:
            discord = _discord_module()
            if discord and isinstance(exc, (discord.Forbidden, discord.NotFound)):
                logger.warning(
                    "Skipping approval result notification for inaccessible channel %s: %s",
                    channel_id,
                    exc,
                )
                return
            if discord and isinstance(exc, discord.HTTPException):
                logger.warning(
                    "Failed to send approval result to channel %s: %s",
                    channel_id,
                    exc,
                )
                return
            logger.exception(
                "Unexpected error sending approval result to channel %s",
                channel_id,
            )
