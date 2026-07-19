"""Evernight Discord adapter — bot riêng cho Evernight.

Listens to DMs and `!9` prefix in any channel.
Compiles native Discord messages into the unified gateway contract before
routing them to Evernight.
Sends bash approval DMs via the same bot.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING

import discord
from discord.ext import commands
from underthesea import sent_tokenize

from gateway.adapters.discord.approval import build_discord_approval_context
from gateway.adapters.discord.adapter import (
    RECONNECT_BASE_DELAY,
    RECONNECT_MAX_DELAY,
    _is_auth_error,
    _is_network_error,
)
from gateway.adapters.discord.converter import DiscordMessageConverter
from gateway.core.handler import GatewayChatHandler
from twin.shared.observability import call_with_langsmith_extra, langsmith_extra
from twin.shared.tools.approval_context import (
    clear_current_approval_context,
    set_current_approval_context,
)

if TYPE_CHECKING:
    from twin.evernight.agent import EvernightAgent

logger = logging.getLogger(__name__)

ERROR_MESSAGE = "Hệ thống não bộ của tớ đang bị quá tải xíu, cậu thử lại sau vài giây nhé!"
EVERNIGHT_PREFIX = "!9"
DEFAULT_OWNER_USER_ID = "726302130318868500"


class _EvernightAgentRouter:
    """Local router that lets Evernight reuse the core gateway chat handler."""

    march7 = None

    def __init__(self, agent: EvernightAgent) -> None:
        self.evernight = agent

    async def route(
        self,
        agent_name: str,
        user_id: str,
        content: str,
        **_: object,
    ) -> str:
        if agent_name != "evernight":
            logger.error("Evernight adapter received unsupported agent route: %s", agent_name)
            return ERROR_MESSAGE

        return await call_with_langsmith_extra(
            self.evernight.handle_chat,
            user_id=user_id,
            content=content,
            langsmith_extra=langsmith_extra(
                tags=["evernight", "discord", "chat"],
                metadata={
                    "workflow": "evernight.discord.chat",
                    "agent_name": "evernight",
                    "user_id": user_id,
                },
            ),
        )


class EvernightDiscordAdapter:
    """Discord bot adapter for Evernight — handles DMs and !9 prefix."""

    EVERNIGHT_PREFIX = EVERNIGHT_PREFIX

    def __init__(
        self,
        token: str,
        agent: EvernightAgent,
        *,
        client_id: str | None = None,
        owner_user_id: str | int | None = None,
        handler: GatewayChatHandler | None = None,
    ):
        self._token = token
        self._agent = agent
        self._client_id = client_id
        self._owner_user_id = str(
            owner_user_id
            or os.getenv("EVERNIGHT_OWNER_USER_ID")
            or DEFAULT_OWNER_USER_ID
        )
        self._handler = handler or GatewayChatHandler(
            agent_router=_EvernightAgentRouter(agent)
        )
        self._task: asyncio.Task | None = None
        self._bot = self._build_bot()

    def _build_bot(self) -> commands.Bot:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        bot = commands.Bot(
            command_prefix="!",
            intents=intents,
            help_command=None,
        )

        @bot.event
        async def on_ready():
            logger.info("Evernight bot ready: %s (ID: %s)", bot.user, bot.user.id)
            await bot.change_presence(
                activity=discord.Game(name="Đang lắng nghe...")
            )

        @bot.event
        async def on_message(message: discord.Message):
            if message.author.bot:
                return
            await self._on_message(message)

        return bot

    async def _on_message(self, message: discord.Message):
        """Handle incoming Discord messages for Evernight — owner only."""
        content = message.content.strip()
        if not content:
            return

        # Owner-only check
        if str(message.author.id) != self._owner_user_id:
            return

        is_dm = message.guild is None
        is_mentioned = self._bot.user in message.mentions if self._bot.user else False
        lower_content = content.lower()
        has_prefix = lower_content.startswith(EVERNIGHT_PREFIX) and (
            len(content) == 2 or content[2] == " "
        )

        # Only process DMs, mentions, or !9 prefix
        if not (is_dm or is_mentioned or has_prefix):
            return

        # Strip mention
        if is_mentioned and self._bot.user:
            content = content.replace(f"<@{self._bot.user.id}>", "")
            content = content.replace(f"<@!{self._bot.user.id}>", "")

        # Strip !9 prefix
        stripped = content.strip()
        lower_stripped = stripped.lower()
        if lower_stripped.startswith(EVERNIGHT_PREFIX):
            if len(stripped) > 2 and stripped[2] == " ":
                content = stripped[3:].strip()
            else:
                content = stripped[2:].strip()
        else:
            content = stripped

        user_id = str(message.author.id)
        logger.info("Evernight routing: user=%s content=%.80s", user_id, content)

        try:
            unified = DiscordMessageConverter.to_unified(
                message,
                bot_user=self._bot.user,
                content_override=content,
            )
            exts = dict(unified.extensions or {})
            bot_user = self._bot.user
            exts.update(
                {
                    "agent_name": "evernight",
                    "assistant_id": str(bot_user.id) if bot_user else None,
                    "assistant_name": bot_user.display_name if bot_user else None,
                    "bot_name": "evernight",
                    "bot_display_name": bot_user.display_name if bot_user else None,
                    "is_addressed": True,
                    "is_mentioned": is_mentioned,
                    "should_respond": True,
                    "observe": False,
                    "allow_silence": False,
                    "respond_mode": "respond",
                    "conversation_id": str(message.channel.id) if message.guild else None,
                    "space_id": str(message.guild.id) if message.guild else None,
                }
            )
            object.__setattr__(unified, "extensions", exts)

            set_current_approval_context(build_discord_approval_context(message))
            try:
                async with message.channel.typing():
                    response = await self._handler.handle_message(unified)
            finally:
                clear_current_approval_context()

            if response:
                await self._send_response(message, response)
        except Exception:
            logger.exception("Error processing Evernight message")
            try:
                await message.channel.send(ERROR_MESSAGE)
            except Exception:
                logger.exception("Failed to send error message")

    async def _send_response(self, original_message: discord.Message, response_text: str):
        """Send response, splitting long messages into chunks."""
        if not response_text:
            return

        clean_text = response_text.replace("\\n", "\n")
        messages_to_send = [msg.strip() for msg in clean_text.split("\n") if msg.strip()]

        from twin.shared.config.settings import Config

        for i, msg_text in enumerate(messages_to_send):
            if len(msg_text) <= 2000:
                await original_message.channel.send(msg_text)
            else:
                chunks = self._chunk_text(msg_text, limit=1900)
                for chunk in chunks:
                    await original_message.channel.send(chunk)

            if i < len(messages_to_send) - 1:
                async with original_message.channel.typing():
                    await asyncio.sleep(Config.PART_BREAK_DELAY)

    @staticmethod
    def _chunk_text(text: str, limit: int = 1900) -> list[str]:
        lines = text.split("\n")
        chunks = []
        current_chunk = ""

        for line in lines:
            if len(current_chunk) + len(line) + 1 <= limit:
                current_chunk += line + "\n"
                continue

            if current_chunk.strip():
                chunks.append(current_chunk.strip())
                current_chunk = ""

            if len(line) <= limit:
                current_chunk = line + "\n"
            else:
                sentences = sent_tokenize(line)
                for sentence in sentences:
                    if len(sentence) > limit:
                        if current_chunk.strip():
                            chunks.append(current_chunk.strip())
                            current_chunk = ""
                        for i in range(0, len(sentence), limit):
                            chunks.append(sentence[i : i + limit])
                    elif len(current_chunk) + len(sentence) + 1 > limit:
                        chunks.append(current_chunk.strip())
                        current_chunk = sentence + " "
                    else:
                        current_chunk += sentence + " "

                current_chunk += "\n"

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        return chunks

    async def send_dm(self, user_id: int, content: str):
        """Send a DM to a specific user (used for bash approval, notifications)."""
        try:
            user = await self._bot.fetch_user(user_id)
            await user.send(content)
        except discord.Forbidden:
            logger.warning("Cannot send DM to user %s (DMs disabled)", user_id)
        except Exception:
            logger.exception("Failed to send DM to user %s", user_id)

    async def connect(self) -> None:
        """Start the Discord bot."""
        if not self._token:
            raise RuntimeError("Evernight Discord token not set")
        self._task = asyncio.create_task(self._run_supervised(self._token))
        logger.info("Evernight adapter: bot.start() task created")

    async def _run_supervised(self, token: str) -> None:
        """Run bot.start() and auto-reconnect through login-time failures.

        Mirrors DiscordPlatformAdapter._run_supervised: discord.py's
        reconnect=True does not cover the initial login(), so a DNS failure at
        container boot would kill the bot permanently without this loop.
        """
        attempt = 0
        while True:
            try:
                await self._bot.start(token, reconnect=True)
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if _is_auth_error(exc):
                    logger.error("Evernight Discord auth error (not retrying): %s", exc)
                    return
                if _is_network_error(exc):
                    logger.warning("Evernight Discord connection lost (network error): %s", exc)
                else:
                    logger.exception("Evernight bot task exited with error")
                delay = min(RECONNECT_BASE_DELAY * (2 ** attempt), RECONNECT_MAX_DELAY)
                attempt += 1
                logger.info(
                    "Reconnecting Evernight Discord bot in %.1fs (attempt %d)",
                    delay, attempt,
                )
                await asyncio.sleep(delay)
                try:
                    await self._bot.close()
                except Exception:
                    pass
                self._bot.clear()

    async def disconnect(self) -> None:
        """Stop the Discord bot."""
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._bot.close()
        logger.info("Evernight adapter disconnected")

    @property
    def is_connected(self) -> bool:
        return self._bot.is_ready()

    @property
    def bot(self) -> commands.Bot:
        """Expose the underlying bot for cog loading."""
        return self._bot
