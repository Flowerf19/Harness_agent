"""Platform-neutral agent router used by gateway handlers."""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from twin.shared.observability import call_with_langsmith_extra, langsmith_extra

if TYPE_CHECKING:
    from gateway.core.evernight_client import EvernightClient
    from twin.march7.agent import March7Agent

logger = logging.getLogger(__name__)


class AgentRouter:
    """Routes messages to the appropriate agent."""

    def __init__(
        self,
        march7: March7Agent,
        evernight_client: EvernightClient | None = None,
    ) -> None:
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
        mentioned_users: list[dict[str, Any]] | None = None,
    ) -> str:
        """Route message to the specified agent."""
        extra = langsmith_extra(
            tags=["gateway", "router", agent_name],
            metadata={
                "workflow": "gateway.route_agent",
                "agent_name": agent_name,
                "user_id": user_id,
                "channel_id": channel_id,
                "guild_id": guild_id,
                "allow_silence": allow_silence,
            },
        )
        if agent_name == "evernight":
            if self.evernight_client is None:
                logger.error("Evernight client not configured - cannot route to Evernight")
                return "Xin lỗi, Evernight hiện chưa được cấu hình."
            return await call_with_langsmith_extra(
                self.evernight_client.send_chat,
                user_id=user_id,
                content=content,
                langsmith_extra=extra,
            )

        return await call_with_langsmith_extra(
            self.march7.handle_chat,
            user_id=user_id,
            content=content,
            channel_id=channel_id,
            observe_input=observe_input,
            guild_id=guild_id,
            bot_id=bot_id,
            bot_name=bot_name,
            allow_silence=allow_silence,
            user_name=user_name,
            mentioned_users=mentioned_users,
            langsmith_extra=extra,
        )

    async def close(self) -> None:
        """Shutdown resources."""
        if self.evernight_client:
            await self.evernight_client.close()
