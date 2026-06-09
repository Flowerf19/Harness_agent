"""Unit tests for DiscordGatewayHandler._send_response flood guard.

A degenerate (looping) LLM response can produce dozens of lines; the handler
must cap how many parts it sends so it cannot spam a channel.
"""
from __future__ import annotations

import pytest

from gateway.adapters.discord.handler import DiscordGatewayHandler, MAX_REPLY_PARTS


class _FakeTyping:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeChannel:
    def __init__(self):
        self.sent: list[str] = []

    async def send(self, content: str):
        self.sent.append(content)

    def typing(self):
        return _FakeTyping()


class _FakeMessage:
    def __init__(self):
        self.channel = _FakeChannel()


@pytest.mark.asyncio
async def test_send_response_caps_flood():
    handler = DiscordGatewayHandler(agent_router=None)
    message = _FakeMessage()
    # 50 short lines → would be 50 separate sends without the cap.
    response = "\n".join(f"Tôi đang ở đây nè {i}" for i in range(50))

    await handler._send_response(message, response)

    assert len(message.channel.sent) == MAX_REPLY_PARTS


@pytest.mark.asyncio
async def test_send_response_normal_reply_unaffected():
    handler = DiscordGatewayHandler(agent_router=None)
    message = _FakeMessage()
    response = "câu một\ncâu hai"

    await handler._send_response(message, response)

    assert message.channel.sent == ["câu một", "câu hai"]


@pytest.mark.asyncio
async def test_send_response_empty_sends_nothing():
    handler = DiscordGatewayHandler(agent_router=None)
    message = _FakeMessage()

    await handler._send_response(message, "")

    assert message.channel.sent == []
