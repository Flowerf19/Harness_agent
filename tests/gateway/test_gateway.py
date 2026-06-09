"""Unit tests for the gateway orchestrator using mock adapters."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from gateway.gateway import ChatGateway
from gateway.shared.adapter_base import PlatformAdapter
from gateway.shared.handler_base import GatewayHandler
from gateway.shared.model import UnifiedChannel, UnifiedEvent, UnifiedMessage, UnifiedUser
from twin.shared.tools.exceptions import BashExecutorUnavailableError


def _make_user() -> UnifiedUser:
    return UnifiedUser(platform_id="u1", platform_name="mock", display_name="User")


def _make_channel() -> UnifiedChannel:
    return UnifiedChannel(channel_id="c1", platform_name="mock", channel_type="dm")


def _make_message() -> UnifiedMessage:
    return UnifiedMessage(
        message_id="m1",
        user=_make_user(),
        channel=_make_channel(),
        content="Hello",
        timestamp=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Mock adapter — concrete implementation of the abstract base
# ---------------------------------------------------------------------------

class MockAdapter(PlatformAdapter):
    """A fake platform adapter that satisfies the PlatformAdapter contract."""

    def __init__(self, connect_raises: Exception | None = None) -> None:
        self._connected = False
        self._connect_raises = connect_raises
        self.sent_messages: list[UnifiedMessage] = []

    async def connect(self) -> None:
        if self._connect_raises:
            raise self._connect_raises
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def send_message(self, msg: UnifiedMessage) -> str:
        self.sent_messages.append(msg)
        return f"sent-{msg.message_id}"


# ---------------------------------------------------------------------------
# Mock handler — concrete implementation of the abstract base
# ---------------------------------------------------------------------------

class MockHandler(GatewayHandler):
    """A fake handler that records calls."""

    def __init__(self) -> None:
        self.handle_message_calls: list[UnifiedMessage] = []
        self.handle_event_calls: list[tuple[UnifiedEvent, UnifiedMessage]] = []
        self._response = "Bot says hi"
        self._raise: Exception | None = None

    async def handle_message(self, msg: UnifiedMessage) -> str:
        self.handle_message_calls.append(msg)
        if self._raise:
            raise self._raise
        return self._response

    async def handle_event(self, event: UnifiedEvent, msg: UnifiedMessage) -> None:
        self.handle_event_calls.append((event, msg))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestChatGateway:
    @pytest.fixture
    def handler(self) -> MockHandler:
        return MockHandler()

    @pytest.fixture
    def gateway(self, handler: MockHandler) -> ChatGateway:
        return ChatGateway(handler)

    def test_register_adapter(self, gateway: ChatGateway):
        adapter = MockAdapter()
        gateway.register_adapter("mock", adapter)
        assert "mock" in gateway.adapter_names
        assert gateway.get_adapter("mock") is adapter

    @pytest.mark.asyncio
    async def test_unregister_adapter(self, gateway: ChatGateway):
        adapter = MockAdapter()
        gateway.register_adapter("mock", adapter)
        gateway.unregister_adapter("mock")
        assert "mock" not in gateway.adapter_names
        # Give the background _safe_disconnect task a chance to run.
        await asyncio.sleep(0.01)

    def test_unregister_unknown_adapter(self, gateway: ChatGateway):
        # Should not raise.
        gateway.unregister_adapter("nonexistent")

    @pytest.mark.asyncio
    async def test_route_message(self, gateway: ChatGateway, handler: MockHandler):
        adapter = MockAdapter()
        gateway.register_adapter("mock", adapter)

        msg = _make_message()
        await gateway.route_message("mock", msg)

        assert len(handler.handle_message_calls) == 1
        assert handler.handle_message_calls[0] is msg
        assert len(adapter.sent_messages) == 1

    @pytest.mark.asyncio
    async def test_route_message_unknown_platform(self, gateway: ChatGateway, handler: MockHandler):
        # Should not raise — just logs a warning.
        msg = _make_message()
        await gateway.route_message("nonexistent", msg)
        assert len(handler.handle_message_calls) == 0

    @pytest.mark.asyncio
    async def test_route_message_handler_error(self, gateway: ChatGateway, handler: MockHandler):
        adapter = MockAdapter()
        gateway.register_adapter("mock", adapter)
        handler._raise = RuntimeError("handler boom")

        msg = _make_message()
        # Should not propagate the exception.
        await gateway.route_message("mock", msg)
        # Adapter should not have sent a message since handler failed.
        assert len(adapter.sent_messages) == 0

    @pytest.mark.asyncio
    async def test_route_message_propagates_platform_capability_error(
        self, gateway: ChatGateway, handler: MockHandler
    ):
        adapter = MockAdapter()
        gateway.register_adapter("mock", adapter)
        handler._raise = BashExecutorUnavailableError("http://bash-executor")

        with pytest.raises(BashExecutorUnavailableError):
            await gateway.route_message("mock", _make_message())

        assert len(adapter.sent_messages) == 0

    @pytest.mark.asyncio
    async def test_route_event(self, gateway: ChatGateway, handler: MockHandler):
        msg = _make_message()
        await gateway.route_event("mock", UnifiedEvent.TYPING, msg)
        assert len(handler.handle_event_calls) == 1
        assert handler.handle_event_calls[0] == (UnifiedEvent.TYPING, msg)

    @pytest.mark.asyncio
    async def test_start_all_and_stop_all(self, gateway: ChatGateway):
        adapter = MockAdapter()
        gateway.register_adapter("mock", adapter)

        await gateway.start_all()
        assert adapter.is_connected

        await gateway.stop_all()
        assert not adapter.is_connected

    @pytest.mark.asyncio
    async def test_start_all_one_adapter_fails(self, gateway: ChatGateway, handler: MockHandler):
        good = MockAdapter()
        bad = MockAdapter(connect_raises=RuntimeError("connect boom"))

        gateway.register_adapter("good", good)
        gateway.register_adapter("bad", bad)

        # Should not raise — bad adapter failure is isolated.
        await gateway.start_all()
        assert good.is_connected
        assert not bad.is_connected
