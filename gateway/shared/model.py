"""Unified, platform-agnostic message models.

All platform adapters translate their native message formats into these
dataclasses before handing them to the gateway orchestrator.  This keeps
the core brain (ChatCoordinator, MemoryManager, LLM services, MCP tools)
completely unaware of any specific platform.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class UnifiedEvent(enum.Enum):
    """Types of events that platform adapters can emit."""

    MESSAGE = "message"
    EDIT = "edit"
    DELETE = "delete"
    REACTION_ADD = "reaction_add"
    REACTION_REMOVE = "reaction_remove"
    JOIN = "join"
    LEAVE = "leave"
    TYPING = "typing"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class UnifiedUser:
    """Represents a message author or participant across any platform."""

    platform_id: str
    """Unique user identifier on the originating platform."""

    platform_name: str
    """Platform name, e.g. ``"discord"``, ``"zalo"``."""

    display_name: str
    """Human-readable display name."""

    avatar_url: Optional[str] = None
    """URL to the user's avatar image (may be ``None``)."""

    is_bot: bool = False
    """Whether this user represents an automated bot."""

    raw_data: Optional[dict] = None
    """Platform-specific user payload preserved for advanced use-cases."""


@dataclass(frozen=True)
class UnifiedChannel:
    """Represents a conversation context on any platform."""

    channel_id: str
    """Unique channel/conversation identifier on the originating platform."""

    platform_name: str
    """Platform name, e.g. ``"discord"``, ``"zalo"``."""

    channel_type: str
    """One of: ``"dm"``, ``"group"``, ``"guild"``, ``"thread"``."""

    name: Optional[str] = None
    """Human-readable channel name (``None`` for DMs)."""

    raw_data: Optional[dict] = None
    """Platform-specific channel payload preserved for advanced use-cases."""


@dataclass(frozen=True)
class UnifiedMessage:
    """A normalised message that any platform adapter can produce or consume."""

    message_id: str
    """Unique message identifier on the originating platform."""

    user: UnifiedUser
    """The author of this message."""

    channel: UnifiedChannel
    """The channel/conversation this message belongs to."""

    content: str
    """The textual body of the message."""

    timestamp: datetime
    """When the message was created/sent (timezone-aware preferred)."""

    attachments: list[dict] = field(default_factory=list)
    """List of attachment metadata dicts (url, filename, size, mime_type, …)."""

    mentions: list[UnifiedUser] = field(default_factory=list)
    """Users mentioned within this message."""

    reply_to: Optional[str] = None
    """``message_id`` of the message this one replies to, if any."""

    extensions: Optional[dict] = None
    """Platform-specific extra data (e.g. Discord embeds, Zalo stickers)."""

    raw_data: Optional[dict] = None
    """The complete native platform message object, preserved for edge cases."""
