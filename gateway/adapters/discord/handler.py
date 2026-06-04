"""Discord-specific gateway handler.

Receives :class:`UnifiedMessage` objects from the Discord adapter,
applies Discord-specific filtering (DMs, mentions, admin channels),
routes the content to the appropriate A2A agent, and returns the response.
"""

from __future__ import annotations

import asyncio
import logging
import os
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

# Wait this long after a message before replying, coalescing a burst of rapid
# messages in the same scope into a single reply (the latest message wins).
MESSAGE_DEBOUNCE_SECONDS = float(os.getenv("MESSAGE_DEBOUNCE_SECONDS", "2.0"))
# Cap reply parts so a degenerate (looping) LLM response can't flood a channel.
MAX_REPLY_PARTS = 5


class DiscordGatewayHandler(GatewayHandler):
    """Handles unified messages from the Discord adapter."""

    _bot: commands.Bot | None = None

    def __init__(self, agent_router: AgentRouter | None = None):
        self._agent_router = agent_router
        # Per-scope serialization + debounce state. Scope = channel (guild) or
        # user (DM), matching the memory scope.
        self._scope_locks: dict[str, asyncio.Lock] = {}
        self._latest_msg: dict[str, str] = {}
        self._burst_addressed: dict[str, bool] = {}

    @staticmethod
    def _scope_key(raw_message: discord.Message, is_dm: bool, user_id: str) -> str:
        if not is_dm and raw_message.guild:
            return f"channel:{raw_message.channel.id}"
        return f"dm:{user_id}"

    def _get_lock(self, scope_key: str) -> asyncio.Lock:
        lock = self._scope_locks.get(scope_key)
        if lock is None:
            lock = asyncio.Lock()
            self._scope_locks[scope_key] = lock
        return lock

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

        # Debounce: coalesce a burst of rapid messages in this scope into one
        # reply. Mark this message the latest, remember if any burst message
        # addressed the bot, then wait — if a newer message arrives, drop this
        # one (the newer message handles the whole burst).
        scope_key = self._scope_key(raw_message, is_dm, user_id)
        self._latest_msg[scope_key] = msg.message_id
        self._burst_addressed[scope_key] = (
            self._burst_addressed.get(scope_key, False) or is_addressed
        )

        await asyncio.sleep(MESSAGE_DEBOUNCE_SECONDS)
        if self._latest_msg.get(scope_key) != msg.message_id:
            return ""

        # Serialize per scope so two turns of the same conversation never run
        # concurrently. Re-check after acquiring: a newer message may have
        # arrived while a previous turn held the lock.
        async with self._get_lock(scope_key):
            if self._latest_msg.get(scope_key) != msg.message_id:
                return ""
            # In a respond channel, March7 may stay silent on ambient messages,
            # but if anything in the burst addressed it, it always replies.
            addressed = self._burst_addressed.pop(scope_key, False)
            allow_silence = is_respond_channel and not addressed

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
                            user_name=msg.user.display_name,
                            mentioned_users=[
                                {
                                    "user_id": mention.platform_id,
                                    "display_name": mention.display_name,
                                    "is_bot": mention.is_bot,
                                }
                                for mention in msg.mentions
                                if not mention.is_bot
                                and mention.platform_id != msg.user.platform_id
                            ],
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
                        user_name=raw_message.author.display_name,
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

        # Flood guard: a degenerate (looping) LLM response can produce dozens of
        # lines. Cap the number of parts so it can't spam the channel.
        if len(messages_to_send) > MAX_REPLY_PARTS:
            logger.warning(
                "Reply has %d parts, capping to %d (possible degenerate output)",
                len(messages_to_send), MAX_REPLY_PARTS,
            )
            messages_to_send = messages_to_send[:MAX_REPLY_PARTS]

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
