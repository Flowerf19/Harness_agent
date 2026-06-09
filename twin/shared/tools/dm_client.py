"""DMClient — HTTP client from March7 to send DMs via Evernight bot.

Used by ApprovalGate and other components that need to send direct messages
to users through Evernight's owner bot.
Supports both general messages and approval requests (with buttons).
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import aiohttp

from twin.shared.tools.approval_context import ApprovalRequestContext

logger = logging.getLogger(__name__)

# Default owner ID for DM approval. Today this is a Discord user ID because the
# Evernight DM backend is Discord-based; callers should treat it as a platform
# user ID.
DEFAULT_USER_ID = 726302130318868500


class DMUnavailableError(Exception):
    """Raised when Evernight bot is not available for DM."""
    pass


# Backward compatibility alias
ApprovalDMUnavailableError = DMUnavailableError


class DMClient:
    """HTTP client that sends DMs via Evernight bot."""

    def __init__(self, evernight_url: str = "http://evernight:8001", timeout: float = 120.0):
        self.base_url = evernight_url.rstrip("/")
        self._timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self._timeout)
            )
        return self._session

    async def send_message(
        self,
        user_id: int,
        content: str,
    ) -> bool:
        """Send a general DM via Evernight bot.

        Args:
            user_id: platform user ID to send DM to
            content: Message content

        Returns:
            True if sent successfully, False otherwise
        """
        session = await self._get_session()
        url = f"{self.base_url}/dm"

        payload = {
            "user_id": user_id,
            "content": content,
            "type": "message",
        }

        logger.info(
            "Sending DM: user=%s content=%.60s",
            user_id, content,
        )

        try:
            async with session.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
            ) as resp:
                if resp.status == 200:
                    logger.info("DM sent successfully")
                    return True
                elif resp.status == 503:
                    logger.warning("Evernight bot not available for DM")
                    raise DMUnavailableError(
                        f"Evernight bot at {self.base_url} is not available for DM"
                    )
                else:
                    error_text = await resp.text()
                    logger.error(
                        "DM request failed: status=%s body=%s",
                        resp.status, error_text[:500],
                    )
                    raise DMUnavailableError(
                        f"DM request failed: HTTP {resp.status}"
                    )
        except DMUnavailableError:
            raise
        except aiohttp.ClientConnectionError:
            logger.error("Cannot connect to Evernight at %s for DM", self.base_url)
            raise DMUnavailableError(
                f"Cannot connect to Evernight at {self.base_url}"
            )
        except Exception:
            logger.exception("Unexpected error in DM request")
            raise DMUnavailableError("Unexpected error in DM request")

    async def request_approval(
        self,
        command: str,
        context: ApprovalRequestContext | None = None,
        user_id: int | None = None,
        *,
        original_message: object | None = None,
        channel_id: str | int | None = None,
        message_id: str | int | None = None,
        channel_name: str | None = None,
    ) -> bool:
        """Request approval DM via Evernight bot.

        Args:
            command: The bash command to approve
            context: Neutral approval context for the triggering message.
            user_id: Platform owner ID to send DM to.
            original_message: Legacy native message shim.
            channel_id: Optional source channel/conversation ID override.
            message_id: Optional source message ID override.
            channel_name: Optional display label for the source conversation.

        Returns:
            True if approved, False if rejected or timeout
        """
        session = await self._get_session()
        url = f"{self.base_url}/dm"
        target_user_id = user_id or _default_owner_user_id()

        if context is None and original_message is not None:
            context = _context_from_native_message(original_message)

        if context is not None:
            channel_id = channel_id or context.channel_id or context.conversation_id
            message_id = message_id or context.message_id
            channel_name = channel_name or context.channel_name

        channel_name = channel_name or "unknown"

        payload = {
            "user_id": target_user_id,
            "command": command,
            "channel_id": _coerce_int_if_numeric(channel_id),
            "message_id": _coerce_int_if_numeric(message_id),
            "channel_name": channel_name,
            "type": "approval",
        }

        logger.info(
            "Requesting approval DM: user=%s channel=%s command=%.60s",
            target_user_id, channel_id, command,
        )

        try:
            async with session.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    approved = data.get("approved", False)
                    logger.info("Approval DM result: %s", "approved" if approved else "rejected")
                    return approved
                elif resp.status == 503:
                    logger.warning("Evernight bot not available for approval DM")
                    raise DMUnavailableError(
                        f"Evernight bot at {self.base_url} is not available for approval DM"
                    )
                else:
                    error_text = await resp.text()
                    logger.error(
                        "Approval DM request failed: status=%s body=%s",
                        resp.status, error_text[:500],
                    )
                    raise DMUnavailableError(
                        f"Approval DM request failed: HTTP {resp.status}"
                    )
        except DMUnavailableError:
            raise
        except aiohttp.ClientConnectionError:
            logger.error("Cannot connect to Evernight at %s for approval DM", self.base_url)
            raise DMUnavailableError(
                f"Cannot connect to Evernight at {self.base_url}"
            )
        except Exception:
            logger.exception("Unexpected error in approval DM request")
            raise DMUnavailableError("Unexpected error in approval DM request")

    async def close(self):
        """Close the underlying HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()


def _context_from_native_message(message: object) -> ApprovalRequestContext:
    """Build neutral context from a legacy native message object."""
    channel = getattr(message, "channel", None)
    guild = getattr(message, "guild", None)
    author = getattr(message, "author", None)
    channel_name = str(channel) if channel is not None else None
    if channel is not None and getattr(channel, "name", None):
        channel_name = f"#{channel.name}"
    if guild is not None and channel_name:
        channel_name = f"{getattr(guild, 'name', guild)}/{channel_name}"

    channel_id = str(getattr(channel, "id", "")) if channel is not None else None
    return ApprovalRequestContext(
        platform="discord",
        user_id=str(getattr(author, "id", "")),
        conversation_id=channel_id,
        channel_id=channel_id,
        message_id=str(getattr(message, "id", "")),
        channel_name=channel_name,
        space_id=str(getattr(guild, "id", "")) if guild is not None else None,
        user_name=getattr(author, "display_name", None),
        native_message=message,
    )


def _coerce_int_if_numeric(value: str | int | None) -> str | int | None:
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return value


def _default_owner_user_id() -> int:
    raw = os.getenv("EVERNIGHT_OWNER_USER_ID")
    if raw and raw.isdigit():
        return int(raw)
    return DEFAULT_USER_ID


# Backward compatibility alias
ApprovalDMClient = DMClient
