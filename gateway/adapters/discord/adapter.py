"""Discord platform adapter implementation.

Wraps the existing ``CoreBot`` class from ``src.bot`` so that the
multi-platform gateway can route messages through the same Discord
connection without duplicating any connection logic.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import discord

from gateway.shared.adapter_base import PlatformAdapter
from gateway.adapters.discord.converter import DiscordMessageConverter

if TYPE_CHECKING:
    from gateway.gateway import ChatGateway
    from gateway.shared.model import UnifiedMessage
    from gateway.shared.core_bot import CoreBot

logger = logging.getLogger(__name__)


class DiscordPlatformAdapter(PlatformAdapter):
    """Adapter that bridges the existing Discord ``CoreBot`` with the gateway."""

    def __init__(
        self,
        bot: CoreBot,
        gateway: ChatGateway,
        bot_name: str = "march7",
    ) -> None:
        self._bot = bot
        self._gateway = gateway
        self._bot_name = bot_name
        self._task: asyncio.Task | None = None
        self._setup_done = False
        self._register_events()
        self._bot.setup_hook = self._gateway_setup_hook

    def _register_events(self) -> None:
        """Attach discord.py event listeners that forward to the gateway."""

        @self._bot.event
        async def on_disconnect():
            logger.warning("Discord gateway disconnected — reconnecting automatically...")

        @self._bot.event
        async def on_resumed():
            logger.info("Discord gateway reconnected (resumed session)")

        @self._bot.event
        async def on_message(message: discord.Message):
            if message.author.bot:
                return

            ctx = await self._bot.get_context(message)
            if ctx.valid:
                return

            content = message.content
            is_mentioned = self._bot.user in message.mentions
            if is_mentioned:
                content = content.replace(f"<@{self._bot.user.id}>", "")
                content = content.replace(f"<@!{self._bot.user.id}>", "")

            try:
                unified = DiscordMessageConverter.to_unified(
                    message,
                    bot_user=self._bot.user,
                    content_override=content.strip(),
                )
                exts = dict(unified.extensions or {})
                exts["bot_name"] = self._bot_name
                object.__setattr__(unified, "extensions", exts)
                await self._gateway.route_message(f"discord_{self._bot_name}", unified)
            except Exception:
                logger.exception("Error forwarding Discord message to gateway")

    async def _gateway_setup_hook(self):
        """Override CoreBot.setup_hook - load cogs only, no AppContainer init."""
        if self._setup_done:
            return

        self._setup_done = True
        logger.info(f"Gateway setup for {self._bot_name} bot: loading cogs")

        from gateway.adapters.discord.handler import DiscordGatewayHandler
        DiscordGatewayHandler.set_bot(self._bot)

        from discord.ext.commands.errors import ExtensionAlreadyLoaded

        for cog_path in (
            "gateway.adapters.discord.cogs.admin_channels",
        ):
            try:
                await self._bot.load_extension(cog_path)
                logger.info("Loaded cog: %s", cog_path)
            except ExtensionAlreadyLoaded:
                logger.debug("Cog already loaded: %s", cog_path)
            except Exception:
                logger.exception("Failed to load cog: %s", cog_path)

    # ------------------------------------------------------------------
    # PlatformAdapter interface
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Start the Discord bot via ``bot.start()``."""
        from twin.shared.config.settings import Config

        # Determine which token to use
        if self._bot_name == "evernight":
            import os
            token = os.getenv("DISCORD_EVERNIGHT_TOKEN", Config.DISCORD_BOT_TOKEN)
        else:
            token = Config.DISCORD_BOT_TOKEN

        if not token:
            raise RuntimeError(f"Discord token not set for {self._bot_name} bot")

        self._task = asyncio.create_task(self._bot.start(token))
        self._task.add_done_callback(self._on_bot_done)
        logger.info(f"Discord adapter: {self._bot_name} bot.start() task created")

    def _on_bot_done(self, task: asyncio.Task) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            logger.info(f"Discord bot {self._bot_name} task cancelled")
        except Exception as exc:
            self._classify_bot_error(exc)

    def _classify_bot_error(self, exc: Exception) -> None:
        error_str = str(exc).lower()
        if any(kw in error_str for kw in (
            "name resolution", "gaierror", "connectordnserror",
            "connection refused", "network is unreachable",
            "temporary failure", "ssl handshake",
        )):
            logger.warning(f"Discord connection lost (network error) for {self._bot_name}: {exc}")
        elif any(kw in error_str for kw in (
            "privileged intent", "disallowed intent",
            "token is invalid", "login failed",
        )):
            logger.error(f"Discord auth error for {self._bot_name}: {exc}")
        else:
            logger.exception(f"Discord bot {self._bot_name} task exited with error")

    async def disconnect(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._bot.close()
        logger.info(f"Discord adapter {self._bot_name} disconnected")

    @property
    def is_connected(self) -> bool:
        return self._bot.is_ready()

    async def send_message(self, msg: UnifiedMessage) -> str:
        """Send *msg* back to the Discord channel it came from."""
        kwargs = DiscordMessageConverter.from_unified(msg)

        channel_id = int(msg.channel.channel_id)
        channel = self._bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self._bot.fetch_channel(channel_id)
            except discord.NotFound:
                logger.warning("Channel %s not found", channel_id)
                return ""
            except discord.HTTPException:
                logger.exception("HTTP error fetching channel %s", channel_id)
                return ""

        if channel is None:
            return ""

        try:
            sent_msg = await channel.send(**kwargs)
            return str(sent_msg.id)
        except discord.HTTPException:
            logger.exception("Failed to send Discord message to channel %s", channel_id)
            return ""
