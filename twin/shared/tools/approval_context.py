"""Platform-neutral approval context for dangerous tool execution.

Gateway adapters set this context before routing a message into the agent.
Shared tools read only neutral metadata and an optional approval backend.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ApprovalRequestContext:
    """Neutral metadata for requesting user approval.

    `native_message` is intentionally opaque. Only the platform adapter/backend
    that created it should inspect it.
    """

    platform: str
    user_id: str
    conversation_id: str | None = None
    channel_id: str | None = None
    message_id: str | None = None
    channel_name: str | None = None
    space_id: str | None = None
    user_name: str | None = None
    native_message: object | None = None
    approval_backend: "ApprovalBackend | None" = None


@runtime_checkable
class ApprovalBackend(Protocol):
    """Platform adapter capability for rendering approval UI."""

    async def request_channel_approval(
        self,
        context: ApprovalRequestContext,
        command: str,
    ) -> bool:
        """Ask for approval in the source conversation/channel."""


_current_approval_context: ContextVar[ApprovalRequestContext | None] = ContextVar(
    "current_approval_context", default=None
)


def set_current_approval_context(context: ApprovalRequestContext) -> None:
    """Set the active approval context for the current task."""
    _current_approval_context.set(context)


def get_current_approval_context() -> ApprovalRequestContext | None:
    """Return the active approval context, if one exists."""
    return _current_approval_context.get(None)


def clear_current_approval_context() -> None:
    """Clear the active approval context."""
    _current_approval_context.set(None)


def set_current_message(message: object) -> None:
    """Compatibility shim for old Discord call sites.

    New code should set a full ApprovalRequestContext from the platform adapter.
    """
    channel = getattr(message, "channel", None)
    guild = getattr(message, "guild", None)
    author = getattr(message, "author", None)
    channel_name = str(channel) if channel is not None else None
    if channel is not None and getattr(channel, "name", None):
        channel_name = f"#{channel.name}"
    if guild is not None and channel_name:
        channel_name = f"{getattr(guild, 'name', guild)}/{channel_name}"

    context = ApprovalRequestContext(
        platform="discord",
        user_id=str(getattr(author, "id", "")),
        conversation_id=str(getattr(channel, "id", "")) if channel is not None else None,
        channel_id=str(getattr(channel, "id", "")) if channel is not None else None,
        message_id=str(getattr(message, "id", "")),
        channel_name=channel_name,
        space_id=str(getattr(guild, "id", "")) if guild is not None else None,
        user_name=getattr(author, "display_name", None),
        native_message=message,
        approval_backend=None,
    )
    set_current_approval_context(context)


def get_current_message() -> object | None:
    """Compatibility shim returning the opaque native message."""
    context = get_current_approval_context()
    if context is None:
        return None
    return context.native_message


def clear_current_message() -> None:
    """Compatibility shim for old Discord call sites."""
    clear_current_approval_context()
