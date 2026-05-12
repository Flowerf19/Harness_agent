"""EvernightClient — A2A HTTP client for March7 container to call Evernight.

Sends JSON-RPC `tasks/send` requests to the Evernight A2A server
running in a separate container.
"""
from __future__ import annotations

import logging

from twin.shared.a2a.client import A2AClient

logger = logging.getLogger(__name__)


class EvernightClient:
    """A2A HTTP client that communicates with the Evernight agent."""

    def __init__(self, base_url: str = "http://evernight:8001", timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self._client = A2AClient(base_url=self.base_url, timeout=timeout)

    async def send_chat(self, user_id: str, content: str) -> str:
        """Send a chat message to Evernight and return the response text."""
        try:
            return await self._client.send_text_task(
                skill="chat",
                session_id=user_id,
                text=content,
            )
        except Exception:
            logger.exception("Failed to send chat to Evernight at %s", self.base_url)
            return "Xin lỗi, không thể kết nối đến Evernight."

    async def health_check(self) -> bool:
        """Check Evernight health via /.well-known/agent.json."""
        try:
            return await self._client.get_agent_card() is not None
        except Exception:
            logger.warning("Evernight health check failed at %s", self.base_url)
            return False

    async def close(self):
        """Close the underlying HTTP session."""
        await self._client.close()
