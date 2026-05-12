"""DMClient — HTTP client from March7 to send DMs via Evernight bot.

Used by ApprovalGate and other components that need to send direct messages
to users through Evernight's Discord bot.
Supports both general messages and approval requests (with buttons).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

import aiohttp

if TYPE_CHECKING:
    import discord

logger = logging.getLogger(__name__)

# Default user ID for DM (the main user)
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
            user_id: Discord user ID to send DM to
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
        original_message: "discord.Message",
        user_id: int = DEFAULT_USER_ID,
    ) -> bool:
        """Request approval DM via Evernight bot.

        Args:
            command: The bash command to approve
            original_message: The original Discord message that triggered this
            user_id: Discord user ID to send DM to

        Returns:
            True if approved, False if rejected or timeout
        """
        session = await self._get_session()
        url = f"{self.base_url}/dm"

        # Extract channel info
        channel = original_message.channel
        channel_id = channel.id
        message_id = original_message.id

        # Build channel name for display in DM
        channel_name = str(channel)
        if hasattr(channel, "name") and channel.name:
            channel_name = f"#{channel.name}"
        if original_message.guild:
            channel_name = f"{original_message.guild.name}/{channel_name}"

        payload = {
            "user_id": user_id,
            "command": command,
            "channel_id": channel_id,
            "message_id": message_id,
            "channel_name": channel_name,
            "type": "approval",
        }

        logger.info(
            "Requesting approval DM: user=%s channel=%s command=%.60s",
            user_id, channel_id, command,
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


# Backward compatibility alias
ApprovalDMClient = DMClient
