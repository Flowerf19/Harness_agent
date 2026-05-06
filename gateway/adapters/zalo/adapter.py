"""Zalo platform adapter — stub implementation.

All connection / sending logic is placeholder until the Zalo API SDK is
identified and integrated.  The adapter satisfies the :class:`PlatformAdapter`
contract so that the gateway can register it without errors.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import aiohttp

from gateway.shared.adapter_base import PlatformAdapter
from gateway.adapters.zalo.converter import ZaloMessageConverter

if TYPE_CHECKING:
    from gateway.shared.model import UnifiedMessage

logger = logging.getLogger(__name__)


class ZaloPlatformAdapter(PlatformAdapter):
    """Stub adapter for the Zalo messaging platform.

    Parameters:
        access_token: Zalo API access token.
        app_id: Zalo application identifier.
    """

    def __init__(self, access_token: str, app_id: str) -> None:
        self._access_token = access_token
        self._app_id = app_id
        self._connected = False
        self._session: aiohttp.ClientSession | None = None

    # ------------------------------------------------------------------
    # PlatformAdapter interface
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Create an HTTP session and log connection (stub)."""
        self._session = aiohttp.ClientSession()
        self._connected = True
        logger.info(
            "Zalo adapter connected (stub) — app_id=%s", self._app_id
        )

    async def disconnect(self) -> None:
        """Close the HTTP session."""
        if self._session:
            await self._session.close()
            self._session = None
        self._connected = False
        logger.info("Zalo adapter disconnected")

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def send_message(self, msg: UnifiedMessage) -> str:
        """Log the message and return a stub message ID.

        Once the Zalo API is available, replace this body with an actual
        HTTP POST to the Zalo send-message endpoint.
        """
        body = ZaloMessageConverter.from_unified(msg)
        logger.info(
            "[ZALO STUB] Would send message %s to thread %s: %r",
            msg.message_id, msg.channel.channel_id, body,
        )
        # Return a stub message ID.
        return f"zalo-stub-{msg.message_id}"

    # on_message / on_edit / on_delete — no-op defaults from base class
    # are sufficient for the scaffold.  A real implementation would
    # register webhook endpoints and forward events to the gateway.
