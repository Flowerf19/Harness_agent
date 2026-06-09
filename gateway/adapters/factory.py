"""Factory function for creating platform adapters from configuration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from gateway.shared.adapter_base import PlatformAdapter
from gateway.config import GatewayConfig

if TYPE_CHECKING:
    from gateway.gateway import ChatGateway

logger = logging.getLogger(__name__)


def create_adapters(
    config: GatewayConfig, gateway: ChatGateway
) -> dict[str, PlatformAdapter]:
    """Create all configured platform adapters."""
    adapters = {}

    if "discord" in config.enabled_platforms:
        discord_adapters = _create_discord_adapters(config, gateway)
        adapters.update(discord_adapters)

    if "zalo" in config.enabled_platforms:
        try:
            adapter = _create_zalo_adapter(config)
            adapters["zalo"] = adapter
        except Exception:
            logger.exception("Failed to create Zalo adapter")

    return adapters


def create_adapter(
    platform: str, config: GatewayConfig, gateway: ChatGateway | None = None
) -> PlatformAdapter:
    """Instantiate a single PlatformAdapter (legacy compatibility)."""
    adapters = create_adapters(config, gateway) if gateway else {}
    if platform in adapters:
        return adapters[platform]

    platform_lower = platform.lower()
    if platform_lower == "discord":
        return _create_discord_adapter(config, gateway)
    elif platform_lower == "zalo":
        return _create_zalo_adapter(config)
    else:
        raise ValueError(f"Unknown platform: {platform!r}")


def _create_discord_adapters(
    config: GatewayConfig, gateway: ChatGateway | None
) -> dict[str, PlatformAdapter]:
    adapters = {}

    # March7 bot (gateway only creates March7 adapter)
    if config.discord_march7_token:
        from gateway.shared.core_bot import CoreBot
        from gateway.adapters.discord.adapter import DiscordPlatformAdapter

        march7_bot = CoreBot()
        adapters["discord_march7"] = DiscordPlatformAdapter(
            bot=march7_bot,
            gateway=gateway,
            bot_name="march7",
        )
        logger.info("Created Discord adapter for March7 bot")

    # Fallback to single bot (legacy)
    if not adapters and config.discord_token:
        from gateway.shared.core_bot import CoreBot
        from gateway.adapters.discord.adapter import DiscordPlatformAdapter

        bot = CoreBot()
        adapters["discord"] = DiscordPlatformAdapter(
            bot=bot,
            gateway=gateway,
            bot_name="march7",
        )
        logger.info("Created Discord adapter (single bot, legacy mode)")

    return adapters


def _create_discord_adapter(
    config: GatewayConfig, gateway: ChatGateway | None
) -> PlatformAdapter:
    """Create a single Discord adapter (legacy)."""
    if not config.discord_token:
        raise RuntimeError(
            "Discord adapter requested but DISCORD_MARCH7_TOKEN is not set"
        )
    if gateway is None:
        raise RuntimeError("Discord adapter requires a gateway instance")

    from gateway.shared.core_bot import CoreBot
    from gateway.adapters.discord.adapter import DiscordPlatformAdapter

    bot = CoreBot()
    return DiscordPlatformAdapter(
        bot=bot,
        gateway=gateway,
        bot_name="march7",
    )


def _create_zalo_adapter(config: GatewayConfig) -> PlatformAdapter:
    raise NotImplementedError(
        "Zalo adapter is planned but not implemented yet. "
        "Keep GATEWAY_ENABLED_PLATFORMS without 'zalo' until Zalo settings "
        "and adapter contract are defined."
    )
