"""Zalo event handler — stub implementation.

Logs all events and returns placeholder responses until the Zalo adapter
is fully integrated with the Zalo API.
"""

from __future__ import annotations

import logging

from gateway.shared.handler_base import GatewayHandler
from gateway.shared.model import UnifiedEvent, UnifiedMessage

logger = logging.getLogger(__name__)


class ZaloEventHandler(GatewayHandler):
    """Stub handler for Zalo unified messages.

    Once the Zalo API is available, this handler will be wired to the
    ``ChatCoordinator`` in the same way as :class:`DiscordGatewayHandler`.
    """

    async def handle_message(self, msg: UnifiedMessage) -> str:
        logger.info(
            "[ZALO STUB] Received message from user %s (%s): %s",
            msg.user.display_name, msg.user.platform_id, msg.content,
        )
        return "[Zalo integration pending — message received]"

    async def handle_event(self, event: UnifiedEvent, msg: UnifiedMessage) -> None:
        logger.debug(
            "[ZALO STUB] Event %s for message %s", event, msg.message_id
        )
