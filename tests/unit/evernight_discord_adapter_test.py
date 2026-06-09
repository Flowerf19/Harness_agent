"""Regression tests for the Evernight Discord compatibility adapter."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from gateway.adapters.discord import evernight_adapter as adapter_module
from gateway.adapters.discord.evernight_adapter import (
    ERROR_MESSAGE,
    EvernightDiscordAdapter,
    _EvernightAgentRouter,
)
from gateway.shared.model import UnifiedChannel, UnifiedMessage, UnifiedUser
from twin.shared.tools.approval_context import (
    ApprovalRequestContext,
    get_current_approval_context,
)


OWNER_USER_ID = "726302130318868500"


class _FakeTyping:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeAvatar:
    url = "https://example.invalid/avatar.png"


class _FakeUser:
    def __init__(
        self,
        user_id: str,
        *,
        display_name: str = "Owner",
        name: str = "owner",
        bot: bool = False,
    ) -> None:
        self.id = int(user_id)
        self.display_name = display_name
        self.name = name
        self.bot = bot
        self.avatar = _FakeAvatar()


class _FakeGuild:
    def __init__(self) -> None:
        self.id = 333
        self.name = "guild"


class _FakeChannel:
    def __init__(self) -> None:
        self.id = 222
        self.name = "general"
        self.sent: list[str] = []

    async def send(self, content: str):
        self.sent.append(content)

    def typing(self):
        return _FakeTyping()


class _FakeMessage:
    def __init__(
        self,
        *,
        content: str,
        guild: _FakeGuild | None,
        mentions: list[_FakeUser] | None = None,
    ) -> None:
        self.id = 111
        self.content = content
        self.author = _FakeUser(OWNER_USER_ID)
        self.channel = _FakeChannel()
        self.guild = guild
        self.mentions = mentions or []
        self.attachments = []
        self.reference = None
        self.created_at = datetime.now(timezone.utc)


class _FakeBot:
    def __init__(self, user: _FakeUser) -> None:
        self.user = user


class _RejectDirectAgent:
    async def handle_chat(self, **kwargs):
        raise AssertionError("Evernight agent must not be called directly by the adapter")


class _SpyHandler:
    def __init__(self) -> None:
        self.messages: list[UnifiedMessage] = []

    async def handle_message(self, msg: UnifiedMessage) -> str:
        self.messages.append(msg)
        return "reply from gate"


class _FakeEvernightAgent:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def handle_chat(self, **kwargs) -> str:
        self.calls.append(kwargs)
        return "evernight reply"


def _fake_to_unified(
    message: _FakeMessage,
    bot_user: _FakeUser | None = None,
    content_override: str | None = None,
) -> UnifiedMessage:
    guild_id = str(message.guild.id) if message.guild else None
    channel_type = "guild" if message.guild else "dm"
    return UnifiedMessage(
        message_id=str(message.id),
        user=UnifiedUser(
            platform_id=str(message.author.id),
            platform_name="discord",
            display_name=message.author.display_name,
        ),
        channel=UnifiedChannel(
            channel_id=str(message.channel.id),
            platform_name="discord",
            channel_type=channel_type,
            name=message.channel.name,
            guild_id=guild_id,
        ),
        content=content_override if content_override is not None else message.content,
        timestamp=message.created_at,
        mentions=[
            UnifiedUser(
                platform_id=str(user.id),
                platform_name="discord",
                display_name=user.display_name,
                is_bot=user.bot,
            )
            for user in message.mentions
        ],
        extensions={},
    )


def _fake_approval_context(message: _FakeMessage) -> ApprovalRequestContext:
    return ApprovalRequestContext(
        platform="discord",
        user_id=str(message.author.id),
        conversation_id=str(message.channel.id),
        channel_id=str(message.channel.id),
        message_id=str(message.id),
        channel_name=f"#{message.channel.name}",
        space_id=str(message.guild.id) if message.guild else None,
    )


@pytest.fixture
def adapter(monkeypatch):
    monkeypatch.setattr(
        adapter_module.DiscordMessageConverter,
        "to_unified",
        staticmethod(_fake_to_unified),
    )
    monkeypatch.setattr(
        adapter_module,
        "build_discord_approval_context",
        _fake_approval_context,
    )

    bot_user = _FakeUser("999", display_name="Evernight", name="evernight", bot=True)
    instance = EvernightDiscordAdapter.__new__(EvernightDiscordAdapter)
    instance._agent = _RejectDirectAgent()
    instance._owner_user_id = OWNER_USER_ID
    instance._handler = _SpyHandler()
    instance._bot = _FakeBot(bot_user)
    return instance


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "guild", "mentions_factory", "expected_content", "expected_mentioned"),
    [
        ("hello in dm", None, lambda bot_user: [], "hello in dm", False),
        ("!9 hello by prefix", _FakeGuild(), lambda bot_user: [], "hello by prefix", False),
        (
            "<@999> hello by tag",
            _FakeGuild(),
            lambda bot_user: [bot_user],
            "hello by tag",
            True,
        ),
    ],
)
async def test_evernight_discord_message_enters_gateway_contract(
    adapter,
    content: str,
    guild: _FakeGuild | None,
    mentions_factory,
    expected_content: str,
    expected_mentioned: bool,
):
    message = _FakeMessage(
        content=content,
        guild=guild,
        mentions=mentions_factory(adapter._bot.user),
    )

    await adapter._on_message(message)

    assert message.channel.sent == ["reply from gate"]
    assert len(adapter._handler.messages) == 1
    unified = adapter._handler.messages[0]
    assert unified.content == expected_content
    assert unified.user.platform_id == OWNER_USER_ID
    assert unified.extensions["agent_name"] == "evernight"
    assert unified.extensions["is_addressed"] is True
    assert unified.extensions["is_mentioned"] is expected_mentioned
    assert unified.extensions["should_respond"] is True
    assert unified.extensions["observe"] is False
    assert unified.extensions["assistant_id"] == "999"
    assert unified.extensions["assistant_name"] == "Evernight"
    assert get_current_approval_context() is None


@pytest.mark.asyncio
async def test_evernight_local_router_only_routes_evernight():
    agent = _FakeEvernightAgent()
    router = _EvernightAgentRouter(agent)

    response = await router.route(
        agent_name="evernight",
        user_id="u1",
        content="hello",
        channel_id="ignored",
    )
    wrong_route = await router.route(
        agent_name="march7",
        user_id="u1",
        content="hello",
    )

    assert response == "evernight reply"
    assert agent.calls == [{"user_id": "u1", "content": "hello"}]
    assert wrong_route == ERROR_MESSAGE
