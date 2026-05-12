"""A2A HTTP client for task submission and SSE result consumption."""
from __future__ import annotations

import json
import logging
import uuid
from typing import AsyncIterator, Optional

import aiohttp

from twin.shared.a2a.types import A2AMessage, A2ATask, AgentCard, Part, TaskStatus

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
            logger.error("Failed to get agent card from %s: %s", self.base_url, e)
            return None

    async def send_task(self, params: dict) -> A2ATask:
        session = await self._get_session()
        payload = {
            "jsonrpc": "2.0",
            "method": "tasks/send",
            "params": params,
            "id": str(uuid.uuid4()),
        }
        async with session.post(
            f"{self.base_url}/",
            json=payload,
            headers={"Content-Type": "application/json"},
        ) as resp:
            data = await resp.json()
            if "result" in data:
                return self._parse_task(data["result"])
            raise RuntimeError(f"A2A error: {data.get('error', data)}")

    async def get_task(self, task_id: str) -> Optional[A2ATask]:
        session = await self._get_session()
        payload = {
            "jsonrpc": "2.0",
            "method": "tasks/get",
            "params": {"id": task_id},
            "id": str(uuid.uuid4()),
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
            logger.error("Failed to get task %s from %s: %s", task_id, self.base_url, e)
            return None

    async def subscribe_stream(self, task_id: str) -> AsyncIterator[A2AMessage]:
        session = await self._get_session()
        async with session.get(
            f"{self.base_url}/tasks/{task_id}/stream",
            headers={"Accept": "text/event-stream"},
            timeout=aiohttp.ClientTimeout(total=self.timeout, sock_read=self.timeout),
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Stream error: {resp.status}")

            buffer = ""
            async for chunk in resp.content.iter_chunked(1024):
                buffer += chunk.decode("utf-8")
                while "\n\n" in buffer:
                    event_str, buffer = buffer.split("\n\n", 1)
                    for line in event_str.split("\n"):
                        if not line.startswith("data: "):
                            continue
                        try:
                            yield self._parse_message(json.loads(line[6:]))
                        except json.JSONDecodeError:
                            continue

    async def send_task_and_wait(self, params: dict) -> list[A2AMessage]:
        if "id" not in params:
            params = {**params, "id": str(uuid.uuid4())}

        task = await self.send_task(params)
        messages: list[A2AMessage] = []
        async for message in self.subscribe_stream(task.id):
            messages.append(message)

        final_task = await self.get_task(task.id)
        if final_task and final_task.status == TaskStatus.FAILED:
            raise RuntimeError(self._last_text(messages) or f"A2A task failed: {task.id}")
        if final_task and final_task.status == TaskStatus.CANCELLED:
            raise RuntimeError(f"A2A task cancelled: {task.id}")
        return messages

    async def send_text_task(
        self,
        *,
        skill: str,
        session_id: str,
        text: str,
        task_id: str | None = None,
    ) -> str:
        messages = await self.send_task_and_wait({
            "id": task_id or str(uuid.uuid4()),
            "sessionId": session_id,
            "skill": skill,
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": text}],
            },
        })
        return self._last_text(messages)

    async def send_data_task(
        self,
        *,
        skill: str,
        session_id: str,
        params: dict | None = None,
        task_id: str | None = None,
    ) -> dict:
        task_params = {
            "id": task_id or str(uuid.uuid4()),
            "sessionId": session_id,
            "skill": skill,
        }
        if params:
            task_params.update(params)

        messages = await self.send_task_and_wait(task_params)
        for message in reversed(messages):
            for part in reversed(message.parts):
                if part.type == "data" and part.data is not None:
                    return part.data
        return {}

    def _parse_task(self, data: dict) -> A2ATask:
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

    @staticmethod
    def _last_text(messages: list[A2AMessage]) -> str:
        for message in reversed(messages):
            texts = [
                part.text
                for part in message.parts
                if part.type == "text" and part.text and part.text.strip() != "..."
            ]
            if texts:
                return "\n".join(texts)
        return ""
