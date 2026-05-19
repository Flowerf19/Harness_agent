from typing import AsyncIterator

import pytest

from twin.shared.a2a.client import A2AClient
from twin.shared.a2a.types import A2AMessage, A2ATask, Part, TaskStatus


class FakeA2AClient(A2AClient):
    def __init__(self, messages: list[A2AMessage], status: TaskStatus = TaskStatus.COMPLETED):
        super().__init__("http://a2a.test")
        self.messages = messages
        self.status = status

    async def send_task(self, params: dict) -> A2ATask:
        return A2ATask(
            id=params["id"],
            session_id=params.get("sessionId"),
            skill=params.get("skill"),
            status=TaskStatus.IN_PROGRESS,
        )

    async def get_task(self, task_id: str) -> A2ATask:
        return A2ATask(id=task_id, status=self.status)

    async def subscribe_stream(self, task_id: str) -> AsyncIterator[A2AMessage]:
        for message in self.messages:
            yield message


@pytest.mark.asyncio
async def test_send_text_task_waits_for_stream_result():
    client = FakeA2AClient([
        A2AMessage(role="agent", parts=[Part(type="text", text="...")]),
        A2AMessage(role="agent", parts=[Part(type="text", text="done")]),
    ])

    result = await client.send_text_task(
        skill="chat",
        session_id="u1",
        text="hello",
    )

    assert result == "done"


@pytest.mark.asyncio
async def test_send_data_task_returns_last_data_part():
    client = FakeA2AClient([
        A2AMessage(role="agent", parts=[Part(type="data", data={"snapshot": [{"role": "user"}]})]),
    ])

    data = await client.send_data_task(skill="get_snapshot", session_id="u1")

    assert data == {"snapshot": [{"role": "user"}]}


@pytest.mark.asyncio
async def test_send_task_and_wait_raises_on_failed_task():
    client = FakeA2AClient(
        [A2AMessage(role="agent", parts=[Part(type="text", text="boom")])],
        status=TaskStatus.FAILED,
    )

    with pytest.raises(RuntimeError, match="boom"):
        await client.send_text_task(skill="chat", session_id="u1", text="hello")
