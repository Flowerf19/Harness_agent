"""Discord-specific gateway handler.

Receives :class:`UnifiedMessage` objects from the Discord adapter,
applies Discord-specific filtering (DMs, mentions, admin channels),
routes the content to the appropriate A2A agent, and returns the response.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from discord.ext import commands
from underthesea import sent_tokenize

from gateway.shared.handler_base import GatewayHandler
from gateway.shared.model import UnifiedEvent, UnifiedMessage
from twin.shared.tools.exceptions import BashExecutorUnavailableError
from twin.shared.tools.approval_context import set_current_message, clear_current_message
from gateway.adapters.discord.cogs.admin_channels import ChannelMode

if TYPE_CHECKING:
    import discord
    from gateway.adapters.discord.agent_router import AgentRouter

logger = logging.getLogger(__name__)

ERROR_MESSAGE = "Hệ thống não bộ của tớ đang bị quá tải xíu, cậu thử lại sau vài giây nhé!"


class DiscordGatewayHandler(GatewayHandler):
    """Handles unified messages from the Discord adapter."""

    _bot: commands.Bot | None = None

    def __init__(self, agent_router: AgentRouter | None = None):
        self._agent_router = agent_router

    async def handle_message(self, msg: UnifiedMessage) -> str:
        raw_message: discord.Message | None = None
        is_mentioned = False
        is_reply_to_bot = False
        if msg.extensions:
            raw_message = msg.extensions.get("_raw_discord_message")
            is_mentioned = msg.extensions.get("is_mentioned", False)
            is_reply_to_bot = msg.extensions.get("is_reply_to_bot", False)

        if raw_message is None:
            logger.warning("No raw Discord message in extensions")
            return ""

        is_dm = msg.channel.channel_type == "dm"

        mode = None
        if raw_message.guild:
            admin_cog = self._get_bot().get_cog("AdminChannels")
            if admin_cog:
                mode = admin_cog.get_mode(
                    raw_message.guild.id, raw_message.channel.id
                )

        if not is_dm and mode is None:
            if is_mentioned or is_reply_to_bot:
                await raw_message.channel.send(
                    "Kênh này tớ chưa được cấu hình hoạt động á. "
                    "Cậu dùng `/addbotchannel` hoặc qua kênh đã set giúp tớ nhé!"
                )
            return ""

        is_respond_channel = mode == ChannelMode.RESPOND_ALLOWED
        is_addressed = is_dm or is_mentioned or is_reply_to_bot
        should_respond = is_addressed or is_respond_channel
        # In a respond channel, ambient (non-addressed) messages are routed too,
        # but March7 may stay silent based on context. Direct address always replies.
        allow_silence = is_respond_channel and not is_addressed

        # Content check
        content = msg.content.strip()
        if not content:
            return ""

        user_id = msg.user.platform_id
        await self._observe_message(
            msg=msg,
            raw_message=raw_message,
            is_dm=is_dm,
            content=content,
        )

        if not should_respond:
            return ""

        # Route to March7 agent (all messages here are non-!9)
        try:
            set_current_message(raw_message)
            logger.info("Routing to march7 agent: user=%s content=%.80s", user_id, content)
            bot_user = self._get_bot().user if self._get_bot() else None
            async with raw_message.channel.typing():
                if self._agent_router:
                    response = await self._agent_router.route(
                        agent_name="march7",
                        user_id=user_id,
                        content=content,
                        channel_id=(
                            str(raw_message.channel.id)
                            if raw_message.guild
                            else None
                        ),
                        observe_input=False,
                        guild_id=(
                            str(raw_message.guild.id)
                            if raw_message.guild
                            else None
                        ),
                        bot_id=str(bot_user.id) if bot_user else None,
                        bot_name=bot_user.display_name if bot_user else None,
                        allow_silence=allow_silence,
                    )
                else:
                    response = await self._legacy_process(user_id, content)

            logger.info("Got response from march7: %.80s", response)
            await self._send_response(raw_message, response)
        except BashExecutorUnavailableError:
            await self._handle_bash_executor_unavailable(raw_message, user_id, content)
        except Exception:
            logger.exception("Error processing message")
            try:
                await raw_message.channel.send(ERROR_MESSAGE)
            except Exception:
                logger.exception("Failed to send error message to user")
        finally:
            clear_current_message()

        return ""

    async def _observe_message(
        self,
        msg: UnifiedMessage,
        raw_message: discord.Message,
        is_dm: bool,
        content: str,
    ) -> None:
        if not self._agent_router:
            return
        memory = getattr(getattr(self._agent_router, "march7", None), "memory", None)
        if memory is None:
            return

        if is_dm or not raw_message.guild:
            await memory.observe_user_message(
                user_id=msg.user.platform_id,
                role="user",
                content=content,
            )
            return

        await memory.observe_channel_message(
            guild_id=str(raw_message.guild.id),
            channel_id=str(raw_message.channel.id),
            author_id=msg.user.platform_id,
            author_name=msg.user.display_name,
            message_id=msg.message_id,
            content=content,
            reply_to=msg.reply_to,
        )

    async def _legacy_process(self, user_id: str, content: str) -> str:
        return ERROR_MESSAGE

    async def handle_event(self, event: UnifiedEvent, msg: UnifiedMessage) -> None:
        logger.debug("Discord event %s for message %s (no-op)", event, msg.message_id)

    # ------------------------------------------------------------------
    # Bash Executor unavailable handling
    # ------------------------------------------------------------------

    async def _handle_bash_executor_unavailable(
        self,
        raw_message: discord.Message,
        user_id: str,
        content: str,
    ) -> None:
        from gateway.adapters.discord.views.bash_executor_start import (
            BashExecutorStartView,
        )

        view = BashExecutorStartView(
            handler=self,
            raw_message=raw_message,
            user_id=user_id,
            content=content,
        )
        await raw_message.channel.send(
            "⚠️ **Host tool chưa sẵn sàng.**\n"
            "Nếu bạn vừa khởi động lại hệ thống, hãy đợi Docker khởi động xong rồi bấm thử lại.",
            view=view,
        )

    async def retry_process_message(
        self,
        raw_message: discord.Message,
        user_id: str,
        content: str,
    ) -> None:
        bot_name = "march7"
        try:
            set_current_message(raw_message)
            async with raw_message.channel.typing():
                if self._agent_router:
                    response = await self._agent_router.route(
                        agent_name=bot_name,
                        user_id=user_id,
                        content=content,
                    )
                else:
                    response = await self._legacy_process(user_id, content)

            await self._send_response(raw_message, response)
        except Exception:
            logger.exception("Retry process_message failed")
            try:
                await raw_message.channel.send(ERROR_MESSAGE)
            except Exception:
                logger.exception("Failed to send error message to user")
        finally:
            clear_current_message()

    # ------------------------------------------------------------------
    # Response sending
    # ------------------------------------------------------------------

    async def _send_response(
        self, original_message: discord.Message, response_text: str
    ) -> None:
        if not response_text:
            return

        clean_text = response_text.replace("\\n", "\n")
        messages_to_send = [
            msg.strip() for msg in clean_text.split("\n") if msg.strip()
        ]

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
    def _chunk_text(text: str, limit: int = 1900) -> list:
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

    @classmethod
    def set_bot(cls, bot: commands.Bot) -> None:
        cls._bot = bot

    @classmethod
    def _get_bot(cls) -> commands.Bot | None:
        return cls._bot
