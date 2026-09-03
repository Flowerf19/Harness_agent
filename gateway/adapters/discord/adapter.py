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

from gateway.adapters.discord.cogs.admin_channels import ChannelMode
from gateway.shared.adapter_base import PlatformAdapter
from gateway.adapters.discord.approval import build_discord_approval_context
from gateway.adapters.discord.connect import supervise_bot
from gateway.adapters.discord.converter import DiscordMessageConverter
from twin.shared.tools.approval_context import (
    clear_current_approval_context,
    set_current_approval_context,
)

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

            # clean_content resolves mentions to readable "@name"/"#channel"
            # (guild-nick aware) so the model knows who a message refers to,
            # instead of seeing raw "<@id>". Does not touch markdown.
            content = message.clean_content

            # Ignore !9 prefix — let Evernight bot handle it directly
            if content.strip().lower().startswith("!9"):
                return

            bot_user = self._bot.user
            is_mentioned = bot_user in message.mentions if bot_user else False
            if is_mentioned:
                # The bot's own mention is now "@<display name>"; strip it so the
                # message reads naturally. Other users' mentions stay resolved.
                bot_names = {bot_user.display_name} if bot_user else set()
                if message.guild and message.guild.me:
                    bot_names.add(message.guild.me.display_name)
                for name in bot_names:
                    content = content.replace(f"@{name}", "")

            try:
                mode = self._channel_mode(message)
                is_reply_to_bot = self._is_reply_to_bot(message)
                is_dm = message.guild is None

                if not is_dm and mode is None:
                    if is_mentioned or is_reply_to_bot:
                        await message.channel.send(
                            "Kênh này tớ chưa được cấu hình hoạt động á. "
                            "Cậu dùng `/addbotchannel` hoặc qua kênh đã set giúp tớ nhé!"
                        )
                    return

                is_respond_channel = mode == ChannelMode.RESPOND_ALLOWED
                is_addressed = is_dm or is_mentioned or is_reply_to_bot
                should_respond = is_addressed or is_respond_channel

                unified = DiscordMessageConverter.to_unified(
                    message,
                    bot_user=bot_user,
                    content_override=content.strip(),
                )
                exts = dict(unified.extensions or {})
                exts.update(
                    {
                        "agent_name": "march7",
                        "assistant_id": str(bot_user.id) if bot_user else None,
                        "assistant_name": bot_user.display_name if bot_user else None,
                        "bot_name": self._bot_name,
                        "bot_display_name": bot_user.display_name if bot_user else None,
                        "is_addressed": is_addressed,
                        "is_mentioned": is_mentioned,
                        "is_reply_to_bot": is_reply_to_bot,
                        "should_respond": should_respond,
                        "allow_silence": is_respond_channel and not is_addressed,
                        "respond_mode": "respond" if is_respond_channel else "observe",
                        "channel_mode": mode.value if mode else None,
                        "conversation_id": str(message.channel.id) if message.guild else None,
                        "space_id": str(message.guild.id) if message.guild else None,
                    }
                )
                object.__setattr__(unified, "extensions", exts)

                set_current_approval_context(build_discord_approval_context(message))
                if should_respond:
                    async with message.channel.typing():
                        await self._gateway.route_message(
                            f"discord_{self._bot_name}", unified
                        )
                else:
                    await self._gateway.route_message(
                        f"discord_{self._bot_name}", unified
                    )
                clear_current_approval_context()
            except Exception:
                clear_current_approval_context()
                logger.exception("Error forwarding Discord message to gateway")

    def _channel_mode(self, message: discord.Message) -> ChannelMode | None:
        if not message.guild:
            return None

        admin_cog = self._bot.get_cog("AdminChannels")
        if not admin_cog:
            return None
        return admin_cog.get_mode(message.guild.id, message.channel.id)

    def _is_reply_to_bot(self, message: discord.Message) -> bool:
        bot_user = self._bot.user
        if bot_user is None or message.reference is None:
            return False

        ref = message.reference
        if ref.cached_message:
            return ref.cached_message.author.id == bot_user.id
        if ref.resolved and hasattr(ref.resolved, "author"):
            return ref.resolved.author.id == bot_user.id
        return False

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
        """Start the Discord bot under a supervisor that retries failures."""
        from twin.shared.config.settings import Config

        # Determine which token to use
        if self._bot_name == "evernight":
            import os
            token = os.getenv("DISCORD_EVERNIGHT_TOKEN", Config.DISCORD_BOT_TOKEN)
        else:
            token = Config.DISCORD_BOT_TOKEN

        if not token:
            raise RuntimeError(f"Discord token not set for {self._bot_name} bot")

        # bot.start() only survives websocket drops; anything that fails before a
        # socket exists (TLS during login) escapes it and silences the bot.
        self._task = asyncio.create_task(
            supervise_bot(self._bot, token, name=self._bot_name)
        )
        logger.info(f"Discord adapter: {self._bot_name} bot.start() task created")

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
            from gateway.adapters.discord.handler import DiscordGatewayHandler, split_response_text
            from twin.shared.config.settings import Config

            base_kwargs = DiscordMessageConverter.from_unified(msg)
            sent_id = ""
            parts = split_response_text(msg.content)
            for index, part in enumerate(parts):
                kwargs = {**base_kwargs, "content": part}
                if len(part) <= 2000:
                    sent_msg = await channel.send(**kwargs)
                    sent_id = str(sent_msg.id)
                else:
                    for chunk in DiscordGatewayHandler._chunk_text(part, limit=1900):
                        sent_msg = await channel.send(**{**kwargs, "content": chunk})
                        sent_id = str(sent_msg.id)

                if index < len(parts) - 1:
                    async with channel.typing():
                        await asyncio.sleep(Config.PART_BREAK_DELAY)

            return sent_id
        except discord.HTTPException:
            logger.exception("Failed to send Discord message to channel %s", channel_id)
            return ""
