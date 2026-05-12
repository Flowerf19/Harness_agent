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
        bot_name = "march7"
        if msg.extensions:
            raw_message = msg.extensions.get("_raw_discord_message")
            is_mentioned = msg.extensions.get("is_mentioned", False)
            bot_name = msg.extensions.get("bot_name", "march7")

        if raw_message is None:
            logger.warning("No raw Discord message in extensions")
            return ""

        # Channel/DM/Mention filtering
        is_dm = msg.channel.channel_type == "dm"

        is_allowed_channel = False
        if raw_message.guild:
            admin_cog = self._get_bot().get_cog("AdminChannels")
            if admin_cog:
                is_allowed_channel = admin_cog.is_bot_channel(
                    raw_message.guild.id, raw_message.channel.id
                )
            else:
                is_allowed_channel = True

        if not (is_dm or is_mentioned or is_allowed_channel):
            return ""

        # Content check
        content = msg.content.strip()
        if not content:
            return ""

        # Detect Evernight prefix: !en, !e
        lower_content = content.lower()
        if lower_content.startswith(("!en", "!e", "!en ", "!e ")):
            bot_name = "evernight"
            # Strip prefix
            for pattern in ("!en", "!e", "!en ", "!e "):
                if lower_content.startswith(pattern):
                    content = content[len(pattern):].strip()
                    break

        user_id = msg.user.platform_id

        # Route to appropriate agent in-process
        try:
            set_current_message(raw_message)
            logger.info("Routing to %s agent: user=%s content=%.80s", bot_name, user_id, content)
            async with raw_message.channel.typing():
                if self._agent_router:
                    response = await self._agent_router.route(
                        agent_name=bot_name,
                        user_id=user_id,
                        content=content,
                    )
                else:
                    response = await self._legacy_process(user_id, content)

            logger.info("Got response from %s: %.80s", bot_name, response)
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
