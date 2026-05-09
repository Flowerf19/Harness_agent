"""A2A HTTP client for sending tasks and subscribing to streams."""
import asyncio
import json
import logging
from typing import AsyncIterator, Optional

import aiohttp

from twin.shared.a2a.types import A2AMessage, A2ATask, AgentCard, Part

logger = logging.getLogger(__name__)


class A2AClient:
    def __init__(self, base_url: str, timeout: float = 300.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_agent_card(self) -> Optional[AgentCard]:
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/.well-known/agent.json") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return AgentCard(**data)
                return None
        except Exception as e:
            logger.error(f"Failed to get agent card from {self.base_url}: {e}")
            return None

    async def send_task(self, params: dict) -> A2ATask:
        session = await self._get_session()
        payload = {
            "jsonrpc": "2.0",
            "method": "tasks/send",
            "params": params,
        }
        try:
            async with session.post(
                f"{self.base_url}/",
                json=payload,
                headers={"Content-Type": "application/json"},
            ) as resp:
                data = await resp.json()
                if "result" in data:
                    return self._parse_task(data["result"])
                raise RuntimeError(f"A2A error: {data.get('error', data)}")
        except Exception as e:
            logger.error(f"Failed to send task to {self.base_url}: {e}")
            raise

    async def get_task(self, task_id: str) -> Optional[A2ATask]:
        session = await self._get_session()
        payload = {
            "jsonrpc": "2.0",
            "method": "tasks/get",
            "params": {"id": task_id},
        }
        try:
            async with session.post(
                f"{self.base_url}/",
                json=payload,
                headers={"Content-Type": "application/json"},
            ) as resp:
                data = await resp.json()
                if "result" in data:
                    return self._parse_task(data["result"])
                return None
        except Exception as e:
            logger.error(f"Failed to get task {task_id}: {e}")
            return None

    async def subscribe_stream(self, task_id: str) -> AsyncIterator[A2AMessage]:
        session = await self._get_session()
        try:
            async with session.get(
                f"{self.base_url}/tasks/{task_id}/stream",
                headers={"Accept": "text/event-stream"},
                timeout=aiohttp.ClientTimeout(total=self.timeout, sock_read=300),
            ) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"Stream error: {resp.status}")

                buffer = ""
                async for chunk in resp.content.iter_chunked(1024):
                    buffer += chunk.decode("utf-8")
                    while "\n\n" in buffer:
                        event_str, buffer = buffer.split("\n\n", 1)
                        for line in event_str.split("\n"):
                            if line.startswith("data: "):
                                try:
                                    data = json.loads(line[6:])
                                    yield self._parse_message(data)
                                except json.JSONDecodeError:
                                    continue
        except Exception as e:
            logger.error(f"Stream error for task {task_id}: {e}")
            raise

    def _parse_task(self, data: dict) -> A2ATask:
        from twin.shared.a2a.types import TaskStatus

        task = A2ATask(
            id=data.get("id", ""),
            session_id=data.get("sessionId"),
            skill=data.get("skill"),
            status=TaskStatus(data.get("status", "pending")),
            artifacts=data.get("artifacts", []),
            metadata=data.get("metadata", {}),
        )

        if "message" in data:
            task.message = self._parse_message(data["message"])

        return task

    def _parse_message(self, data: dict) -> A2AMessage:
        parts = []
        for p in data.get("parts", []):
            parts.append(Part(
                type=p.get("type", "text"),
                text=p.get("text"),
                data=p.get("data"),
                file_url=p.get("file_url"),
            ))
        return A2AMessage(
            role=data.get("role", "agent"),
            parts=parts,
            message_id=data.get("messageId"),
            context_id=data.get("contextId"),
        )
