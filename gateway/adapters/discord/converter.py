"""Converters between Discord native objects and unified models."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord

from gateway.shared.model import UnifiedChannel, UnifiedMessage, UnifiedUser

logger = logging.getLogger(__name__)


class DiscordUserConverter:
    """Translate ``discord.User`` / ``discord.Member`` ↔ :class:`UnifiedUser`."""

    @staticmethod
    def to_unified(user: discord.abc.User) -> UnifiedUser:
        return UnifiedUser(
            platform_id=str(user.id),
            platform_name="discord",
            display_name=user.display_name if hasattr(user, "display_name") else user.name,
            avatar_url=str(user.avatar.url) if user.avatar else None,
            is_bot=user.bot,
            raw_data={
                "id": user.id,
                "name": user.name,
                "discriminator": getattr(user, "discriminator", "0"),
            },
        )


class DiscordChannelConverter:
    """Translate Discord channel objects ↔ :class:`UnifiedChannel`."""

    @staticmethod
    def to_unified(
        channel: discord.abc.GuildChannel | discord.DMChannel | discord.Thread,
    ) -> UnifiedChannel:
        # Determine channel_type
        if isinstance(channel, discord.DMChannel):
            channel_type = "dm"
        elif isinstance(channel, discord.Thread):
            channel_type = "thread"
        elif getattr(channel, "type", None) == discord.ChannelType.group:
            channel_type = "group"
        else:
            channel_type = "guild"

        guild = getattr(channel, "guild", None)
        guild_id = str(guild.id) if guild is not None else None

        return UnifiedChannel(
            channel_id=str(channel.id),
            platform_name="discord",
            channel_type=channel_type,
            name=getattr(channel, "name", None),
            guild_id=guild_id,
            raw_data={
                "id": channel.id,
                "guild_id": guild_id,
                "type": str(getattr(channel, "type", "unknown")),
            },
        )


class DiscordMessageConverter:
    """Translate ``discord.Message`` ↔ :class:`UnifiedMessage`."""

    @staticmethod
    def to_unified(
        message: discord.Message,
        bot_user: discord.ClientUser | None = None,
        content_override: str | None = None,
    ) -> UnifiedMessage:
        user = DiscordUserConverter.to_unified(message.author)
        channel = DiscordChannelConverter.to_unified(message.channel)

        mentions = [
            DiscordUserConverter.to_unified(u) for u in message.mentions
        ]

        attachments = [
            {
                "url": a.url,
                "filename": a.filename,
                "size": a.size,
                "mime_type": a.content_type,
            }
            for a in message.attachments
        ]

        reply_to = (
            str(message.reference.message_id)
            if message.reference and message.reference.message_id
            else None
        )

        # Handle timestamp — discord.py provides aware datetimes.
        ts = message.created_at
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        # Compute is_mentioned flag
        is_mentioned = False
        if bot_user is not None:
            is_mentioned = bot_user in message.mentions

        is_reply_to_bot = False
        if bot_user is not None and message.reference:
            ref = message.reference
            if ref.cached_message:
                is_reply_to_bot = ref.cached_message.author.id == bot_user.id
            elif ref.resolved and hasattr(ref.resolved, "author"):
                is_reply_to_bot = ref.resolved.author.id == bot_user.id

        # Build extensions with platform-specific data
        extensions = {
            "is_mentioned": is_mentioned,
            "is_reply_to_bot": is_reply_to_bot,
            "_raw_discord_message": message,
        }

        return UnifiedMessage(
            message_id=str(message.id),
            user=user,
            channel=channel,
            content=content_override if content_override is not None else message.content,
            timestamp=ts,
            attachments=attachments,
            mentions=mentions,
            reply_to=reply_to,
            extensions=extensions,
            raw_data=None,  # Could store full message dict if needed.
        )

    @staticmethod
    def from_unified(msg: UnifiedMessage) -> dict:
        """Return kwargs suitable for ``discord.TextChannel.send(**kwargs)``.

        Only the ``content`` field is used here.  Platform-specific rich
        content (embeds, components) should be placed in ``msg.extensions``
        by the calling adapter.
        """
        kwargs: dict = {"content": msg.content}

        # Support Discord embeds via extensions.
        if msg.extensions and "embed" in msg.extensions:
            kwargs["embed"] = msg.extensions["embed"]

        # Support replying to a message.
        if msg.reply_to:
            kwargs["reference"] = msg.reply_to

        return kwargs
