"""Agent Router - routes Discord messages to the correct agent in-process.

Instead of using A2A HTTP (which breaks ContextVar / ApprovalGate),
this router calls agents directly within the same process.

A2A HTTP servers remain available for external callers, but internal
routing uses direct in-process calls.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from twin.march7.agent import March7Agent
    from twin.evernight.agent import EvernightAgent

logger = logging.getLogger(__name__)


class AgentRouter:
    """Routes messages to the appropriate agent (march7 or evernight)."""

    def __init__(
        self,
        march7: March7Agent,
        evernight: EvernightAgent,
    ):
        self.march7 = march7
        self.evernight = evernight

    async def route(self, agent_name: str, user_id: str, content: str) -> str:
        """Route message to the specified agent."""
        if agent_name == "evernight":
            return await self.evernight.handle_chat(user_id=user_id, content=content)
        else:
            # Default to march7
            return await self.march7.handle_chat(user_id=user_id, content=content)

    async def close(self):
        """Shutdown resources."""
        pass  # agents manage their own lifecycle
