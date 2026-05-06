"""Factory function for creating platform adapters from configuration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from gateway.shared.adapter_base import PlatformAdapter
from gateway.config import GatewayConfig

if TYPE_CHECKING:
    from gateway.gateway import ChatGateway

logger = logging.getLogger(__name__)


def create_adapter(
    platform: str, config: GatewayConfig, gateway: ChatGateway | None = None
) -> PlatformAdapter:
    """Instantiate the appropriate :class:`PlatformAdapter` for *platform*.

    Parameters:
        platform: Platform name (``"discord"``, ``"zalo"``).
        config: Gateway configuration object.
        gateway: The ``ChatGateway`` orchestrator (required for Discord).

    Returns:
        A concrete ``PlatformAdapter`` instance.

    Raises:
        ValueError: If *platform* is not recognised.
        RuntimeError: If required configuration for the platform is missing.
    """
    platform_lower = platform.lower()

    if platform_lower == "discord":
        return _create_discord_adapter(config, gateway)
    elif platform_lower == "zalo":
        return _create_zalo_adapter(config)
    else:
        raise ValueError(f"Unknown platform: {platform!r}")


def _create_discord_adapter(
    config: GatewayConfig, gateway: ChatGateway | None
) -> PlatformAdapter:
    """Create the Discord platform adapter."""
    if not config.discord_token:
        raise RuntimeError(
            "Discord adapter requested but DISCORD_LLM_BOT_TOKEN is not set"
        )
    if gateway is None:
        raise RuntimeError(
            "Discord adapter requires a gateway instance — pass gateway=... to create_adapter()"
        )

    # Lazy imports to avoid pulling in discord.py / src/ at module level.
    from src.bot import CoreBot
    from gateway.adapters.discord.adapter import DiscordPlatformAdapter

    bot = CoreBot()
    return DiscordPlatformAdapter(bot, gateway)


def _create_zalo_adapter(config: GatewayConfig) -> PlatformAdapter:
    """Create the Zalo platform adapter (stub)."""
    from gateway.adapters.zalo.adapter import ZaloPlatformAdapter

    if not config.zalo_access_token:
        logger.warning(
            "Zalo adapter requested but ZALO_ACCESS_TOKEN is not set — using empty token"
        )

    return ZaloPlatformAdapter(
        access_token=config.zalo_access_token,
        app_id=config.zalo_app_id,
    )
