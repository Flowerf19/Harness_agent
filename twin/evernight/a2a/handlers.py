"""Evernight A2A skill handlers."""

import logging
from typing import AsyncIterator

from twin.evernight.agent import EvernightAgent
from twin.shared.a2a.types import A2AMessage, Part

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
        logger.info("Evernight handling chat for user %s", user_id)

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
        reason = params.get("reason", "manual")
        max_messages = params.get("max_messages", 200)

        logger.info(
            "Evernight handling consolidation via tool for user %s, reason=%s",
            session_id,
            reason,
        )
        try:
            result = await self.agent.consolidate_via_tool(
                scope="user",
                scope_id=session_id,
                reason=reason,
                max_messages=max_messages,
            )
            yield A2AMessage(
                role="agent",
                parts=[Part(type="data", data=result)],
            )
        except Exception as e:
            logger.exception("Consolidation handler error")
            yield A2AMessage(
                role="agent",
                parts=[Part(type="data", data={"status": "failed", "error": str(e)})],
            )

    async def handle_consolidate_discussion_task(
        self, params: dict
    ) -> AsyncIterator[A2AMessage]:
        payload = params.get("payload") or {}
        scope = payload.get("scope", "user")
        scope_id = payload.get("scope_id")
        reason = payload.get("reason", "discussion")
        max_messages = payload.get("max_messages", 200)
        entries = payload.get("entries") or None

        logger.info(
            "Evernight handling consolidate_discussion via tool scope=%s scope_id=%s entries=%d",
            scope,
            scope_id,
            len(entries or []),
        )

        if not scope_id:
            yield A2AMessage(
                role="agent",
                parts=[
                    Part(
                        type="data",
                        data={
                            "status": "failed",
                            "scope": scope,
                            "scope_id": scope_id,
                            "reason": "scope_id required",
                        },
                    )
                ],
            )
            return

        try:
            result = await self.agent.consolidate_via_tool(
                scope=scope,
                scope_id=scope_id,
                reason=reason,
                max_messages=max_messages,
                entries=entries,
            )
            result["scope"] = scope
            result["scope_id"] = scope_id
            yield A2AMessage(
                role="agent",
                parts=[Part(type="data", data=result)],
            )
        except Exception as e:
            logger.exception("Consolidation discussion handler error")
            yield A2AMessage(
                role="agent",
                parts=[
                    Part(
                        type="data",
                        data={
                            "status": "failed",
                            "scope": scope,
                            "scope_id": scope_id,
                            "error": str(e),
                        },
                    )
                ],
            )
