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
    from src.bot import CoreBot

logger = logging.getLogger(__name__)


class DiscordPlatformAdapter(PlatformAdapter):
    """Adapter that bridges the existing Discord ``CoreBot`` with the gateway."""

    def __init__(self, bot: CoreBot, gateway: ChatGateway) -> None:
        self._bot = bot
        self._gateway = gateway
        self._task: asyncio.Task | None = None
        self._setup_done = False
        self._register_events()
        # Override setup_hook so CoreBot doesn't double-init in gateway mode.
        self._bot.setup_hook = self._gateway_setup_hook

    def _register_events(self) -> None:
        """Attach discord.py event listeners that forward to the gateway."""

        @self._bot.event
        async def on_disconnect():
            logger.warning("⚠️ Discord gateway disconnected — reconnecting automatically...")

        @self._bot.event
        async def on_resumed():
            logger.info("✅ Discord gateway reconnected (resumed session)")

        @self._bot.event
        async def on_message(message: discord.Message):
            if message.author.bot:
                return

            # Skip valid bot commands (e.g. !clear, !addbotchannel)
            ctx = await self._bot.get_context(message)
            if ctx.valid:
                return

            # Strip mention tag if bot was mentioned
            content = message.content
            is_mentioned = self._bot.user in message.mentions
            if is_mentioned:
                content = content.replace(f"<@{self._bot.user.id}>", "")

            try:
                unified = DiscordMessageConverter.to_unified(
                    message,
                    bot_user=self._bot.user,
                    content_override=content.strip(),
                )
                await self._gateway.route_message("discord", unified)
            except Exception:
                logger.exception("Error forwarding Discord message to gateway")

    async def _gateway_setup_hook(self):
        """Override CoreBot.setup_hook to prevent double initialization.

        In gateway mode, the adapter handles cog loading, AppContainer init,
        and NightlyTrigger startup in connect().  This hook runs once when
        bot.start() is called — we skip it if already set up.
        """
        if self._setup_done:
            logger.debug("Gateway setup already done — skipping CoreBot.setup_hook")
            return

        self._setup_done = True
        logger.info("Gateway setup: AppContainer, cogs, NightlyTrigger")

        from src.config.settings import Config  # lazy import

        token = Config.DISCORD_BOT_TOKEN
        if not token:
            raise RuntimeError("DISCORD_BOT_TOKEN (DISCORD_LLM_BOT_TOKEN) not set in environment")

        # Initialise the AppContainer (the shared brain) before starting.
        from src.services.dependencies import AppContainer

        container = AppContainer.get_instance()
        await container.initialize()

        # Load cogs — matching the order in CoreBot.setup_hook().
        # Wrapping in try/except to handle reconnection (ExtensionAlreadyLoaded).
        from discord.ext.commands.errors import ExtensionAlreadyLoaded

        for cog_path in ("src.cogs.admin_channels", "src.cogs.user_commands"):
            try:
                await self._bot.load_extension(cog_path)
                logger.info("Loaded cog: %s", cog_path)
            except ExtensionAlreadyLoaded:
                logger.debug("Cog already loaded: %s", cog_path)
            except Exception:
                logger.exception("Failed to load cog: %s", cog_path)

        # Share bot reference with the handler so it can access cogs.
        from gateway.adapters.discord.handler import DiscordGatewayHandler
        DiscordGatewayHandler._bot = self._bot

        # Start NightlyTrigger background task.
        if container.nightly_trigger:
            asyncio.create_task(container.nightly_trigger.start())
            logger.info("NightlyTrigger: started scheduled task")

    # ------------------------------------------------------------------
    # PlatformAdapter interface
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Start the Discord bot via ``bot.start()``.

        ``bot.start()`` triggers ``_gateway_setup_hook()`` which handles
        AppContainer init, cog loading, and NightlyTrigger startup.
        We run it as a background task so ``connect()`` returns immediately.
        """
        from src.config.settings import Config  # lazy import

        token = Config.DISCORD_BOT_TOKEN
        if not token:
            raise RuntimeError("DISCORD_BOT_TOKEN (DISCORD_LLM_BOT_TOKEN) not set in environment")

        # Run bot.start() as a background task.
        self._task = asyncio.create_task(self._bot.start(token))
        self._task.add_done_callback(self._on_bot_done)
        logger.info("Discord adapter: bot.start() task created")

    def _on_bot_done(self, task: asyncio.Task) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            logger.info("Discord bot task cancelled (normal shutdown or reconnect)")
        except Exception as exc:
            self._classify_bot_error(exc)

    def _classify_bot_error(self, exc: Exception) -> None:
        """Classify and log Discord connection errors cleanly."""
        error_str = str(exc).lower()

        # Network / DNS errors — transient, reconnect will handle.
        if any(kw in error_str for kw in (
            "name resolution", "gaierror", "connectordnserror",
            "connection refused", "network is unreachable",
            "temporary failure", "ssl handshake",
        )):
            logger.warning(
                "Discord connection lost (network/DNS error) — gateway will reconnect: %s",
                exc,
            )
        elif any(kw in error_str for kw in (
            "privileged intent", "disallowed intent",
            "token is invalid", "login failed",
        )):
            logger.error(
                "Discord authentication error — check token/intents: %s",
                exc,
            )
        else:
            logger.exception("Discord bot task exited with unexpected error")

    async def disconnect(self) -> None:
        """Shut down the Discord bot connection."""
        # Stop NightlyTrigger background task.
        try:
            from src.services.dependencies import AppContainer
            container = AppContainer.get_instance()
            if container.nightly_trigger and container.nightly_trigger.is_running():
                await container.nightly_trigger.stop()
                logger.info("NightlyTrigger: stopped")
        except Exception:
            logger.exception("Error stopping NightlyTrigger")

        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._bot.close()
        logger.info("Discord adapter disconnected")

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
                logger.warning("Channel %s not found — cannot send reply", channel_id)
                return ""
            except discord.HTTPException:
                logger.exception("HTTP error fetching channel %s", channel_id)
                return ""

        if channel is None:
            logger.warning("Channel %s is None — cannot send reply", channel_id)
            return ""

        try:
            sent_msg = await channel.send(**kwargs)
            return str(sent_msg.id)
        except discord.HTTPException:
            logger.exception("Failed to send Discord message to channel %s", channel_id)
            return ""
