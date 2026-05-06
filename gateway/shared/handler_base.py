"""Abstract base class for gateway-level message/event handlers."""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gateway.shared.model import UnifiedEvent, UnifiedMessage


class GatewayHandler(abc.ABC):
    """Contract for objects that process unified messages from the gateway.

    A handler receives a :class:`UnifiedMessage` and is responsible for
    invoking the platform-agnostic core (ChatCoordinator, MemoryManager, etc.)
    and producing a response string that the adapter can send back.
    """

    @abc.abstractmethod
    async def handle_message(self, msg: UnifiedMessage) -> str:
        """Process *msg* through the core brain and return the response text.

        Implementations typically call ``ChatCoordinator.process_message()``
        here.
        """

    @abc.abstractmethod
    async def handle_event(
        self, event: UnifiedEvent, msg: UnifiedMessage
    ) -> None:
        """Handle a non-message event (edit, delete, reaction, …)."""
