"""Discord-specific gateway handler.

Receives :class:`UnifiedMessage` objects from the Discord adapter,
applies Discord-specific filtering (DMs, mentions, admin channels),
passes the content to ``ChatCoordinator``, and returns the response.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from discord.ext import commands
from underthesea import sent_tokenize

from gateway.shared.handler_base import GatewayHandler
from gateway.shared.model import UnifiedEvent, UnifiedMessage

if TYPE_CHECKING:
    import discord

logger = logging.getLogger(__name__)

# Vietnamese error message shown when coordinator fails.
ERROR_MESSAGE = "Hệ thống não bộ của tớ đang bị quá tải xíu, cậu thử lại sau vài giây nhé!"


class DiscordGatewayHandler(GatewayHandler):
    """Handles unified messages from the Discord adapter.

    This handler replicates the message-filtering logic from the original
    ``src.cogs.chat_gateway.ChatGateway`` cog so that the gateway entry
    point behaves identically to ``python3 -m src``.
    """

    # Set by DiscordPlatformAdapter.connect() after cog loading.
    _bot: commands.Bot | None = None

    async def handle_message(self, msg: UnifiedMessage) -> str:
        # --- Extract raw discord.Message and flags from extensions ---
        raw_message: discord.Message | None = None
        is_mentioned = False
        if msg.extensions:
            raw_message = msg.extensions.get("_raw_discord_message")
            is_mentioned = msg.extensions.get("is_mentioned", False)

        if raw_message is None:
            logger.warning("No raw Discord message in extensions — cannot process")
            return ""

        # --- 1. CHANNEL / MENTION / DM FILTERING ---
        is_dm = msg.channel.channel_type == "dm"

        is_allowed_channel = False
        if raw_message.guild:
            admin_cog = self._get_bot().get_cog("AdminChannels")
            if admin_cog:
                is_allowed_channel = admin_cog.is_bot_channel(
                    raw_message.guild.id, raw_message.channel.id
                )
            else:
                # Fallback: if cog failed to load, default to allow
                is_allowed_channel = True

        if not (is_dm or is_mentioned or is_allowed_channel):
            return ""

        # --- 2. CONTENT CHECK ---
        content = msg.content.strip()
        if not content:
            return ""

        user_id = msg.user.platform_id

        # --- 3. COORDINATOR CALL ---
        coordinator = self._get_coordinator()
        if coordinator is None:
            logger.error("ChatCoordinator not initialised!")
            return ""

        # --- 4. TYPING INDICATOR + COORDINATOR CALL + RESPONSE ---
        try:
            async with raw_message.channel.typing():
                response = await coordinator.process_message(
                    user_id=user_id, content=content
                )
            await self._send_response(raw_message, response)
        except Exception:
            logger.exception("Error in ChatCoordinator.process_message")
            try:
                await raw_message.channel.send(ERROR_MESSAGE)
            except Exception:
                logger.exception("Failed to send error message to user")

        # Handler sends directly via raw channel, so return empty
        # to prevent gateway from double-sending.
        return ""

    async def handle_event(self, event: UnifiedEvent, msg: UnifiedMessage) -> None:
        logger.debug("Discord event %s for message %s (no-op)", event, msg.message_id)

    # ------------------------------------------------------------------
    # Response sending (replicates original ChatGateway._send_response)
    # ------------------------------------------------------------------

    async def _send_response(
        self, original_message: discord.Message, response_text: str
    ) -> None:
        """Split and send response with chunking and typing indicator.

        Replicates the exact logic from ``ChatGateway._send_response``:
        1. Replace literal ``\\n`` with real newlines
        2. Split on newlines
        3. For segments > 2000 chars, use ``_chunk_text()`` hybrid split
        4. Apply typing indicator and PART_BREAK_DELAY between segments
        """
        from src.config.settings import Config

        if not response_text:
            return

        # Step 1: Normalize newlines
        clean_text = response_text.replace("\\n", "\n")

        # Step 2: Split into segments
        messages_to_send = [
            msg.strip() for msg in clean_text.split("\n") if msg.strip()
        ]

        # Step 3: Send each segment
        for i, msg_text in enumerate(messages_to_send):
            if len(msg_text) <= 2000:
                await original_message.channel.send(msg_text)
            else:
                chunks = self._chunk_text(msg_text, limit=1900)
                for chunk in chunks:
                    await original_message.channel.send(chunk)

            # Typing + delay between segments (not after last)
            if i < len(messages_to_send) - 1:
                async with original_message.channel.typing():
                    await asyncio.sleep(Config.PART_BREAK_DELAY)

    # ------------------------------------------------------------------
    # Chunking (exact copy of original ChatGateway._chunk_text)
    # ------------------------------------------------------------------

    @staticmethod
    def _chunk_text(text: str, limit: int = 1900) -> list:
        """Cut string with hybrid splitting: line-based with sent_tokenize fallback."""
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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_coordinator():
        """Lazily fetch the ChatCoordinator from AppContainer."""
        from src.services.dependencies import AppContainer

        return AppContainer.get_instance().chat_coordinator

    @classmethod
    def _get_bot(cls) -> commands.Bot | None:
        """Return the CoreBot instance set by the adapter."""
        return cls._bot
