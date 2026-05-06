"""Abstract base class that every platform adapter must implement."""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gateway.shared.model import UnifiedMessage


class PlatformAdapter(abc.ABC):
    """Contract between the gateway orchestrator and a platform adapter.

    Each concrete adapter wraps its platform's native client/library and
    translates between native objects and :class:`~gateway.shared.model.UnifiedMessage`.
    """

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @abc.abstractmethod
    async def connect(self) -> None:
        """Establish connection to the platform."""

    @abc.abstractmethod
    async def disconnect(self) -> None:
        """Gracefully disconnect from the platform."""

    @property
    @abc.abstractmethod
    def is_connected(self) -> bool:
        """Return ``True`` when the adapter has an active connection."""

    # ------------------------------------------------------------------
    # Outbound (gateway → platform)
    # ------------------------------------------------------------------

    @abc.abstractmethod
    async def send_message(self, msg: UnifiedMessage) -> str:
        """Send *msg* back to the originating platform.

        Returns:
            The platform-native message ID for the sent message.
        """

    # ------------------------------------------------------------------
    # Inbound hooks (platform → gateway)
    # ------------------------------------------------------------------
    # Concrete adapters override these to receive events from their
    # platform and forward them to the gateway via the registered handler.
    # The base class provides no-op defaults so that adapters only need
    # to override the events they care about.

    async def on_message(self, raw_message: object) -> None:
        """Called when a new message arrives from the platform.

        *raw_message* is the native platform object (e.g. ``discord.Message``).
        The adapter should convert it to a :class:`UnifiedMessage` and pass
        it to the gateway's route_message method.
        """

    async def on_edit(self, raw_message: object) -> None:
        """Called when a message is edited on the platform."""

    async def on_delete(self, raw_message: object) -> None:
        """Called when a message is deleted on the platform."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def platform_name(self) -> str:
        """Human-readable platform identifier (used in logging)."""
        return self.__class__.__name__.replace("PlatformAdapter", "").lower()
