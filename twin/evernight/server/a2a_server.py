"""Evernight A2A Server."""
import logging
from typing import AsyncIterator

from twin.shared.a2a.server import A2AServer
from twin.shared.a2a.types import A2AMessage, Part
from twin.evernight.agent import EvernightAgent

logger = logging.getLogger(__name__)


class EvernightA2AHandler:
    def __init__(self, agent: EvernightAgent):
        self.agent = agent

    async def handle_chat_task(self, params: dict) -> AsyncIterator[A2AMessage]:
        session_id = params.get("sessionId", "unknown")
        msg = params.get("message", {})
        parts = msg.get("parts", [])
        content = ""
        for p in parts:
            if p.get("type") == "text":
                content += p.get("text", "")

        user_id = session_id
        logger.info(f"Evernight handling chat for user {user_id}")

        try:
            response = await self.agent.handle_chat(user_id=user_id, content=content)
            yield A2AMessage(
                role="agent",
                parts=[Part(type="text", text=response)],
            )
        except Exception as e:
            logger.exception("Chat handler error")
            yield A2AMessage(
                role="agent",
                parts=[Part(type="text", text=f"Error: {e}")],
            )

    async def handle_consolidate_task(self, params: dict) -> AsyncIterator[A2AMessage]:
        session_id = params.get("sessionId", "unknown")
        snapshot = params.get("snapshot", [])

        logger.info(f"Evernight handling consolidation for user {session_id}")
        try:
            success = await self.agent.consolidate(session_id, snapshot)
            yield A2AMessage(
                role="agent",
                parts=[Part(type="text", text=f"Consolidation {'successful' if success else 'failed'}")],
            )
        except Exception as e:
            yield A2AMessage(
                role="agent",
                parts=[Part(type="text", text=f"Consolidation error: {e}")],
            )


def start_server(agent: EvernightAgent, host="0.0.0.0", port=8001) -> A2AServer:
    handler = EvernightA2AHandler(agent)
    server = A2AServer(
        agent_card=agent.get_agent_card(),
        skill_handlers={
            "chat": handler.handle_chat_task,
            "consolidate": handler.handle_consolidate_task,
        },
        host=host,
        port=port,
    )
    return server
