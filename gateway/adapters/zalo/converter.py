"""Converters between Zalo raw dicts and unified models.

Because the Zalo API SDK is not yet integrated, converters accept and
return plain ``dict`` objects representing the raw JSON payload from Zalo
webhooks / API responses.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from gateway.shared.model import UnifiedChannel, UnifiedMessage, UnifiedUser
from gateway.adapters.zalo.model import ZaloMessageExtension

logger = logging.getLogger(__name__)


class ZaloUserConverter:
    """Translate a Zalo user dict ↔ :class:`UnifiedUser`."""

    @staticmethod
    def to_unified(zalo_user: dict[str, Any]) -> UnifiedUser:
        return UnifiedUser(
            platform_id=str(zalo_user.get("id", "")),
            platform_name="zalo",
            display_name=zalo_user.get("name", "Unknown"),
            avatar_url=zalo_user.get("avatar"),
            is_bot=zalo_user.get("is_bot", False),
            raw_data=zalo_user,
        )


class ZaloChannelConverter:
    """Translate a Zalo conversation dict ↔ :class:`UnifiedChannel`."""

    @staticmethod
    def to_unified(zalo_conversation: dict[str, Any]) -> UnifiedChannel:
        # Zalo has DMs (thread) and group chats.
        thread_type = zalo_conversation.get("thread_type", "dm")
        channel_type = "group" if thread_type == "group" else "dm"

        return UnifiedChannel(
            channel_id=str(zalo_conversation.get("thread_id", "")),
            platform_name="zalo",
            channel_type=channel_type,
            name=zalo_conversation.get("name"),
            raw_data=zalo_conversation,
        )


class ZaloMessageConverter:
    """Translate a Zalo message dict ↔ :class:`UnifiedMessage`."""

    @staticmethod
    def to_unified(zalo_msg: dict[str, Any]) -> UnifiedMessage:
        user_data = zalo_msg.get("sender", zalo_msg.get("user", {}))
        user = ZaloUserConverter.to_unified(user_data)

        conversation_data = zalo_msg.get("conversation", zalo_msg.get("thread", {}))
        channel = ZaloChannelConverter.to_unified(conversation_data)

        content = zalo_msg.get("text", zalo_msg.get("content", ""))

        # Determine message type for extensions.
        msg_type = zalo_msg.get("msg_type", "text")
        ext = ZaloMessageExtension(
            msg_type=msg_type,
            sticker_id=zalo_msg.get("sticker_id"),
            photo_url=zalo_msg.get("photo_url"),
            file_url=zalo_msg.get("file_url"),
        )

        ts_raw = zalo_msg.get("timestamp")
        if ts_raw is not None:
            # Assume Unix timestamp in seconds.
            ts = datetime.fromtimestamp(float(ts_raw), tz=timezone.utc)
        else:
            ts = datetime.now(timezone.utc)

        return UnifiedMessage(
            message_id=str(zalo_msg.get("message_id", "")),
            user=user,
            channel=channel,
            content=content,
            timestamp=ts,
            attachments=zalo_msg.get("attachments", []),
            mentions=[],  # Zalo mention parsing TBD.
            reply_to=zalo_msg.get("reply_to"),
            extensions=ext.to_dict(),
            raw_data=zalo_msg,
        )

    @staticmethod
    def from_unified(msg: UnifiedMessage) -> dict[str, Any]:
        """Build a Zalo API request body from a unified message.

        The exact shape of this dict depends on the Zalo API endpoint
        (e.g. ``/api/message/send``).  Until the SDK is available, we
        return a best-effort structure.
        """
        body: dict[str, Any] = {
            "thread_id": msg.channel.channel_id,
            "text": msg.content,
        }

        # If the message has Zalo extensions, apply them.
        if msg.extensions:
            ext = ZaloMessageExtension.from_dict(msg.extensions)
            if ext.msg_type != "text":
                body["msg_type"] = ext.msg_type
            if ext.sticker_id is not None:
                body["sticker_id"] = ext.sticker_id
            if ext.photo_url is not None:
                body["photo_url"] = ext.photo_url
            if ext.file_url is not None:
                body["file_url"] = ext.file_url

        return body
