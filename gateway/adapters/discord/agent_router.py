"""Agent Router - routes Discord messages to the correct agent in-process.

March7 runs in-process; Evernight is reached via A2A HTTP through
EvernightClient. This keeps the two containers decoupled while
allowing the gateway to route to either one.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from twin.march7.agent import March7Agent
    from gateway.adapters.discord.evernight_client import EvernightClient

logger = logging.getLogger(__name__)


class AgentRouter:
    """Routes messages to the appropriate agent (march7 or evernight)."""

    def __init__(
        self,
        march7: March7Agent,
        evernight_client: EvernightClient | None = None,
    ):
        self.march7 = march7
        self.evernight_client = evernight_client

    async def route(
        self,
        agent_name: str,
        user_id: str,
        content: str,
        *,
        channel_id: str | None = None,
        observe_input: bool = True,
        guild_id: str | None = None,
        bot_id: str | None = None,
        bot_name: str | None = None,
        allow_silence: bool = False,
        user_name: str | None = None,
    ) -> str:
        """Route message to the specified agent."""
        if agent_name == "evernight":
            if self.evernight_client is None:
                logger.error("Evernight client not configured — cannot route to Evernight")
                return "Xin lỗi, Evernight hiện chưa được cấu hình."
            return await self.evernight_client.send_chat(user_id=user_id, content=content)
        else:
            # Default to march7
            return await self.march7.handle_chat(
                user_id=user_id,
                content=content,
                channel_id=channel_id,
                observe_input=observe_input,
                guild_id=guild_id,
                bot_id=bot_id,
                bot_name=bot_name,
                allow_silence=allow_silence,
                user_name=user_name,
            )

    async def close(self):
        """Shutdown resources."""
        if self.evernight_client:
            await self.evernight_client.close()
