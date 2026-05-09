"""Gateway A2A client for routing messages to agents."""
import asyncio
import logging
from typing import Optional
from uuid import uuid4

from twin.shared.a2a.client import A2AClient
from twin.shared.a2a.types import A2AMessage, Part

logger = logging.getLogger(__name__)


class GatewayA2AClient:
    def __init__(self, march7_url: str, evernight_url: str):
        self.march7 = A2AClient(march7_url)
        self.evernight = A2AClient(evernight_url)

    async def close(self):
        await self.march7.close()
        await self.evernight.close()

    async def send_chat_task(
        self,
        agent: str,
        user_id: str,
        content: str,
        msg_extensions: Optional[dict] = None,
    ) -> str:
        client = self.march7 if agent == "march7" else self.evernight

        try:
            task = await client.send_task({
                "id": str(uuid4()),
                "sessionId": user_id,
                "skill": "chat",
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": content}],
                },
            })

            response_parts = []
            async for msg in client.subscribe_stream(task.id):
                for part in msg.parts:
                    if part.type == "text" and part.text:
                        response_parts.append(part.text)

            return "".join(response_parts)

        except Exception as e:
            logger.error(f"GatewayA2AClient: Failed to send chat to {agent}: {e}")
            raise
