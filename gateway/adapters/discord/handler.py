"""Discord compatibility helpers for gateway response/retry behavior.

Production chat routing uses :class:`gateway.core.handler.GatewayChatHandler`.
This module remains in the Discord adapter layer for native Discord concerns:
message splitting, retry UI callbacks, and access to the live discord.py bot.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from discord.ext import commands
from underthesea import sent_tokenize

from gateway.adapters.discord.approval import build_discord_approval_context
from gateway.core.handler import ERROR_MESSAGE, GatewayChatHandler
from twin.shared.tools.approval_context import (
    clear_current_approval_context,
    set_current_approval_context,
)

if TYPE_CHECKING:
    import discord
    from gateway.core.agent_router import AgentRouter

logger = logging.getLogger(__name__)

# Cap reply parts so a degenerate (looping) LLM response can't flood a channel.
MAX_REPLY_PARTS = 5


class DiscordGatewayHandler(GatewayChatHandler):
    """Compatibility wrapper for Discord-specific helper methods."""

    _bot: commands.Bot | None = None

    def __init__(self, agent_router: AgentRouter | None = None) -> None:
        super().__init__(agent_router=agent_router)

    async def retry_process_message(
        self,
        raw_message: discord.Message,
        user_id: str,
        content: str,
    ) -> None:
        """Retry a Discord message from the native Bash Executor retry view."""
        try:
            set_current_approval_context(build_discord_approval_context(raw_message))
            async with raw_message.channel.typing():
                if self._agent_router:
                    response = await self._agent_router.route(
                        agent_name="march7",
                        user_id=user_id,
                        content=content,
                        user_name=raw_message.author.display_name,
                    )
                else:
                    response = ERROR_MESSAGE

            await self._send_response(raw_message, response)
        except Exception:
            logger.exception("Retry process_message failed")
            try:
                await raw_message.channel.send(ERROR_MESSAGE)
            except Exception:
                logger.exception("Failed to send error message to user")
        finally:
            clear_current_approval_context()

    async def _send_response(
        self, original_message: discord.Message, response_text: str
    ) -> None:
        if not response_text:
            return

        from twin.shared.config.settings import Config

        parts = split_response_text(response_text)
        for i, msg_text in enumerate(parts):
            if len(msg_text) <= 2000:
                await original_message.channel.send(msg_text)
            else:
                for chunk in self._chunk_text(msg_text, limit=1900):
                    await original_message.channel.send(chunk)

            if i < len(parts) - 1:
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

    @classmethod
    def set_bot(cls, bot: commands.Bot) -> None:
        cls._bot = bot

    @classmethod
    def _get_bot(cls) -> commands.Bot | None:
        return cls._bot


def split_response_text(response_text: str) -> list[str]:
    """Split a Discord response into flood-guarded message parts."""
    clean_text = response_text.replace("\\n", "\n")
    messages_to_send = [msg.strip() for msg in clean_text.split("\n") if msg.strip()]

    if len(messages_to_send) > MAX_REPLY_PARTS:
        logger.warning(
            "Reply has %d parts, capping to %d (possible degenerate output)",
            len(messages_to_send),
            MAX_REPLY_PARTS,
        )
        messages_to_send = messages_to_send[:MAX_REPLY_PARTS]

    return messages_to_send
