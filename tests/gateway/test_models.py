"""Unit tests for unified message models."""

from datetime import datetime, timezone

import pytest

from gateway.shared.model import UnifiedChannel, UnifiedEvent, UnifiedMessage, UnifiedUser


# ---------------------------------------------------------------------------
# UnifiedUser
# ---------------------------------------------------------------------------

class TestUnifiedUser:
    def test_minimal_fields(self):
        user = UnifiedUser(
            platform_id="123",
            platform_name="discord",
            display_name="Alice",
        )
        assert user.platform_id == "123"
        assert user.platform_name == "discord"
        assert user.display_name == "Alice"
        assert user.avatar_url is None
        assert user.is_bot is False
        assert user.raw_data is None

    def test_all_fields(self):
        raw = {"foo": "bar"}
        user = UnifiedUser(
            platform_id="456",
            platform_name="zalo",
            display_name="Bob",
            avatar_url="https://example.com/avatar.png",
            is_bot=True,
            raw_data=raw,
        )
        assert user.avatar_url == "https://example.com/avatar.png"
        assert user.is_bot is True
        assert user.raw_data is raw

    def test_frozen(self):
        user = UnifiedUser(
            platform_id="1", platform_name="discord", display_name="Test"
        )
        with pytest.raises(AttributeError):
            user.display_name = "Changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# UnifiedChannel
# ---------------------------------------------------------------------------

class TestUnifiedChannel:
    def test_minimal_fields(self):
        ch = UnifiedChannel(
            channel_id="ch1", platform_name="discord", channel_type="dm"
        )
        assert ch.channel_id == "ch1"
        assert ch.name is None
        assert ch.raw_data is None

    def test_all_channel_types(self):
        for ch_type in ("dm", "group", "guild", "thread"):
            ch = UnifiedChannel(
                channel_id="x", platform_name="zalo", channel_type=ch_type
            )
            assert ch.channel_type == ch_type


# ---------------------------------------------------------------------------
# UnifiedMessage
# ---------------------------------------------------------------------------

class TestUnifiedMessage:
    def _make_user(self) -> UnifiedUser:
        return UnifiedUser(
            platform_id="u1", platform_name="discord", display_name="User"
        )

    def _make_channel(self) -> UnifiedChannel:
        return UnifiedChannel(
            channel_id="c1", platform_name="discord", channel_type="dm"
        )

    def test_minimal_fields(self):
        msg = UnifiedMessage(
            message_id="m1",
            user=self._make_user(),
            channel=self._make_channel(),
            content="Hello",
            timestamp=datetime.now(timezone.utc),
        )
        assert msg.message_id == "m1"
        assert msg.content == "Hello"
        assert msg.attachments == []
        assert msg.mentions == []
        assert msg.reply_to is None
        assert msg.extensions is None
        assert msg.raw_data is None

    def test_with_attachments_and_mentions(self):
        user2 = UnifiedUser(
            platform_id="u2", platform_name="discord", display_name="Other"
        )
        msg = UnifiedMessage(
            message_id="m2",
            user=self._make_user(),
            channel=self._make_channel(),
            content="Hi @Other",
            timestamp=datetime.now(timezone.utc),
            attachments=[{"url": "https://example.com/file.png"}],
            mentions=[user2],
            reply_to="m0",
            extensions={"embed": {"title": "Test"}},
        )
        assert len(msg.attachments) == 1
        assert len(msg.mentions) == 1
        assert msg.reply_to == "m0"
        assert msg.extensions["embed"]["title"] == "Test"  # type: ignore[index]


# ---------------------------------------------------------------------------
# UnifiedEvent
# ---------------------------------------------------------------------------

class TestUnifiedEvent:
    def test_all_event_values(self):
        expected = [
            "message", "edit", "delete",
            "reaction_add", "reaction_remove",
            "join", "leave", "typing",
        ]
        actual = [e.value for e in UnifiedEvent]
        assert actual == expected
