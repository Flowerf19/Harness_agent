from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from twin.shared.tools.approval_context import (
    ApprovalRequestContext,
    clear_current_approval_context,
    set_current_approval_context,
)
from twin.shared.tools.approval_gate import ApprovalGate
from twin.shared.tools.dm_client import DMClient


@dataclass
class RecordingBackend:
    result: bool = True
    calls: list[tuple[ApprovalRequestContext, str]] | None = None

    async def request_channel_approval(
        self,
        context: ApprovalRequestContext,
        command: str,
    ) -> bool:
        if self.calls is None:
            self.calls = []
        self.calls.append((context, command))
        return self.result


class FailingDMClient:
    async def request_approval(self, **kwargs: Any) -> bool:
        raise RuntimeError("dm unavailable")


class FakeResponse:
    status = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return {"approved": True}


class FakeSession:
    def __init__(self) -> None:
        self.posts: list[dict[str, Any]] = []

    def post(self, url: str, *, json: dict[str, Any], headers: dict[str, str]):
        self.posts.append({"url": url, "json": json, "headers": headers})
        return FakeResponse()


@pytest.fixture(autouse=True)
def clear_approval_context():
    clear_current_approval_context()
    yield
    clear_current_approval_context()


@pytest.mark.asyncio
async def test_approval_gate_rejects_without_context(monkeypatch):
    monkeypatch.delenv("APPROVAL_AUTO_APPROVE_WITHOUT_CONTEXT", raising=False)

    approved = await ApprovalGate().check_approval("host_system", "pwd")

    assert approved is False


@pytest.mark.asyncio
async def test_approval_gate_uses_context_backend():
    backend = RecordingBackend(result=True)
    context = ApprovalRequestContext(
        platform="test",
        user_id="user-1",
        conversation_id="conversation-1",
        approval_backend=backend,
    )
    set_current_approval_context(context)

    approved = await ApprovalGate().check_approval("host_system", "pwd")

    assert approved is True
    assert backend.calls == [(context, "pwd")]


@pytest.mark.asyncio
async def test_approval_gate_falls_back_to_channel_backend_when_dm_fails():
    backend = RecordingBackend(result=False)
    context = ApprovalRequestContext(
        platform="test",
        user_id="user-1",
        conversation_id="conversation-1",
        approval_backend=backend,
    )
    set_current_approval_context(context)

    approved = await ApprovalGate(dm_client=FailingDMClient()).check_approval(
        "host_system",
        "pwd",
    )

    assert approved is False
    assert backend.calls == [(context, "pwd")]


@pytest.mark.asyncio
async def test_dm_client_request_approval_uses_neutral_context(monkeypatch):
    session = FakeSession()
    client = DMClient(evernight_url="http://evernight.local")

    async def fake_get_session():
        return session

    monkeypatch.setattr(client, "_get_session", fake_get_session)

    context = ApprovalRequestContext(
        platform="discord",
        user_id="123",
        conversation_id="456",
        channel_id="456",
        message_id="789",
        channel_name="Guild/#ops",
    )

    approved = await client.request_approval(
        command="ls -la",
        context=context,
        user_id=123,
    )

    assert approved is True
    assert session.posts == [
        {
            "url": "http://evernight.local/dm",
            "json": {
                "user_id": 123,
                "command": "ls -la",
                "channel_id": 456,
                "message_id": 789,
                "channel_name": "Guild/#ops",
                "type": "approval",
            },
            "headers": {"Content-Type": "application/json"},
        }
    ]
