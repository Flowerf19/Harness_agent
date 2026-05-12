"""Evernight A2A Server."""
import logging
from typing import AsyncIterator, TYPE_CHECKING

from aiohttp import web
from discord.ext import commands

from twin.shared.a2a.server import A2AServer
from twin.shared.a2a.types import A2AMessage, Part
from twin.evernight.agent import EvernightAgent

OWNER_USER_ID = 726302130318868500

logger = logging.getLogger(__name__)


class EvernightA2AHandler:
    def __init__(self, agent: EvernightAgent, discord_bot: commands.Bot | None = None):
        self.agent = agent
        self.discord_bot = discord_bot

    async def handle_chat_task(self, params: dict) -> AsyncIterator[A2AMessage]:
        session_id = params.get("sessionId", "unknown")
        msg = params.get("message", {})
        parts = msg.get("parts", [])
        content = ""
        for p in parts:
            if p.get("type") == "text":
                content += p.get("text", "")

        user_id = session_id
        logger.info(f"Evernight handling chat for user {user_id}")

        try:
            response = await self.agent.handle_chat(user_id=user_id, content=content)
            yield A2AMessage(
                role="agent",
                parts=[Part(type="text", text=response)],
            )
        except Exception as e:
            logger.exception("Chat handler error")
            yield A2AMessage(
                role="agent",
                parts=[Part(type="text", text=f"Error: {e}")],
            )

    async def handle_consolidate_task(self, params: dict) -> AsyncIterator[A2AMessage]:
        session_id = params.get("sessionId", "unknown")
        snapshot = params.get("snapshot", [])

        logger.info(f"Evernight handling consolidation for user {session_id}")
        try:
            success = await self.agent.consolidate(session_id, snapshot)
            yield A2AMessage(
                role="agent",
                parts=[Part(type="text", text=f"Consolidation {'successful' if success else 'failed'}")],
            )
        except Exception as e:
            yield A2AMessage(
                role="agent",
                parts=[Part(type="text", text=f"Consolidation error: {e}")],
            )

    async def handle_dm(self, request: web.Request) -> web.Response:
        """Handle general DM request from March7 container.

        Expects JSON body: {
            "user_id": int,
            "content": str,
            "type": "message" | "approval" (optional, defaults to "message"),
            "channel_id": int (approval only),
            "message_id": int (approval only),
            "channel_name": str (approval only),
            "command": str (approval only),
        }
        Returns: {"success": true} or {"success": false, "error": "..."}
                 For approval type: {"approved": bool}
        """
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"success": False, "error": "Invalid JSON"}, status=400)

        user_id = body.get("user_id")
        content = body.get("content", "")
        msg_type = body.get("type", "message")

        # Owner-only check
        if user_id != OWNER_USER_ID:
            logger.warning("DM rejected for non-owner user_id=%s", user_id)
            return web.json_response({"success": False, "error": "Access denied: owner only"}, status=403)

        if not user_id:
            return web.json_response({"success": False, "error": "Missing user_id"}, status=400)

        if not self.discord_bot:
            logger.warning("Discord bot not available, cannot send DM")
            return web.json_response({"success": False, "error": "Discord bot not available"}, status=503)

        if not self.discord_bot.is_ready():
            logger.warning("Discord bot not ready, cannot send DM")
            return web.json_response({"success": False, "error": "Discord bot not ready"}, status=503)

        try:
            user = await self.discord_bot.fetch_user(user_id)
        except Exception as e:
            logger.exception("Failed to fetch user %s", user_id)
            return web.json_response({"success": False, "error": f"Cannot fetch user: {e}"}, status=500)

        if msg_type == "approval":
            return await self._handle_approval_type_dm(user, body)
        else:
            return await self._handle_message_type_dm(user, content)

    async def _handle_message_type_dm(self, user, content: str) -> web.Response:
        """Send a simple text DM."""
        try:
            await user.send(content)
            return web.json_response({"success": True})
        except Exception as e:
            logger.exception("Error sending DM to user %s", user.id)
            return web.json_response({"success": False, "error": str(e)}, status=500)

    async def _handle_approval_type_dm(self, user, body: dict) -> web.Response:
        """Send an approval DM with buttons."""
        command = body.get("command", "")
        channel_id = body.get("channel_id")
        message_id = body.get("message_id")
        channel_name = body.get("channel_name", "unknown")

        if not command:
            return web.json_response({"success": False, "error": "Missing command for approval"}, status=400)

        try:
            # Import here to avoid circular imports at module level
            from gateway.adapters.discord.views.dm_approve_view import DMApproveView, DM_APPROVAL_TIMEOUT

            view = DMApproveView(command=command)

            dm_content = (
                f"🔐 **Bé Bảy muốn chạy lệnh trên host:**\n"
                f"```bash\n{command[:500]}\n```\n"
                f"📍 Kênh gốc: {channel_name}\n"
                f"Cho phép? (Timeout: {DM_APPROVAL_TIMEOUT} giây)"
            )
            sent_msg = await user.send(dm_content, view=view)

            # Wait for user decision
            approved = await view.wait_for_decision()

            # Clean up the DM message
            try:
                await sent_msg.delete()
            except Exception:
                pass

            # Notify original channel about the result
            if channel_id:
                await self._notify_original_channel(channel_id, message_id, command, approved)

            return web.json_response({"approved": approved})

        except Exception as e:
            logger.exception("Error in approval DM handler")
            return web.json_response({"success": False, "error": str(e)}, status=500)

    async def handle_approval_dm(self, request: web.Request) -> web.Response:
        """Handle bash approval DM request from March7 container.

        DEPRECATED: Use /dm with type="approval" instead.
        Kept for backward compatibility.

        Expects JSON body: {
            "user_id": int,
            "command": str,
            "channel_id": int,
            "message_id": int | null,
            "channel_name": str,
        }
        Returns: {"approved": bool}
        """
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
            # Import here to avoid circular imports at module level
            from gateway.adapters.discord.views.dm_approve_view import DMApproveView, DM_APPROVAL_TIMEOUT

            user = await self.discord_bot.fetch_user(user_id)
            view = DMApproveView(command=command)

            dm_content = (
                f"🔐 **Bé Bảy muốn chạy lệnh trên host:**\n"
                f"```bash\n{command[:500]}\n```\n"
                f"📍 Kênh gốc: {channel_name}\n"
                f"Cho phép? (Timeout: {DM_APPROVAL_TIMEOUT} giây)"
            )
            sent_msg = await user.send(dm_content, view=view)

            # Wait for user decision
            approved = await view.wait_for_decision()

            # Clean up the DM message
            try:
                await sent_msg.delete()
            except Exception:
                pass

            # Notify original channel about the result
            if channel_id:
                await self._notify_original_channel(channel_id, message_id, command, approved)

            return web.json_response({"approved": approved})

        except Exception as e:
            logger.exception("Error in approval_dm handler")
            return web.json_response({"error": str(e)}, status=500)

    async def _notify_original_channel(self, channel_id: int, message_id: int | None, command: str, approved: bool):
        """Send approval result back to the original channel."""
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
        except Exception:
            logger.exception("Failed to send approval result to channel %s", channel_id)


def start_server(agent: EvernightAgent, host="0.0.0.0", port=8001, discord_bot=None) -> A2AServer:
    handler = EvernightA2AHandler(agent, discord_bot=discord_bot)
    server = A2AServer(
        agent_card=agent.get_agent_card(),
        skill_handlers={
            "chat": handler.handle_chat_task,
            "consolidate": handler.handle_consolidate_task,
        },
        host=host,
        port=port,
    )
    # Patch: add the DM endpoints
    original_build_app = server.build_app

    def patched_build_app():
        app = original_build_app()
        app.router.add_post("/dm", handler.handle_dm)
        app.router.add_post("/approval_dm", handler.handle_approval_dm)
        return app

    server.build_app = patched_build_app
    return server
