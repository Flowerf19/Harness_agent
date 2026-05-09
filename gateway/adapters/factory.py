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

    # March7 bot
    if config.discord_march7_token:
        from gateway.shared.core_bot import CoreBot
        from gateway.adapters.discord.adapter import DiscordPlatformAdapter

        march7_bot = CoreBot()
        adapters["discord_march7"] = DiscordPlatformAdapter(
            bot=march7_bot,
            gateway=gateway,
            bot_name="march7",
            agent_url=config.march7_url,
        )
        logger.info("Created Discord adapter for March7 bot")

    # Evernight bot
    if config.discord_evernight_token:
        from gateway.shared.core_bot import CoreBot
        from gateway.adapters.discord.adapter import DiscordPlatformAdapter

        evernight_bot = CoreBot()
        adapters["discord_evernight"] = DiscordPlatformAdapter(
            bot=evernight_bot,
            gateway=gateway,
            bot_name="evernight",
            agent_url=config.evernight_url,
        )
        logger.info("Created Discord adapter for Evernight bot")

    # Fallback to single bot (legacy)
    if not adapters and config.discord_token:
        from gateway.shared.core_bot import CoreBot
        from gateway.adapters.discord.adapter import DiscordPlatformAdapter

        bot = CoreBot()
        adapters["discord"] = DiscordPlatformAdapter(
            bot=bot,
            gateway=gateway,
            bot_name="march7",
            agent_url=config.march7_url,
        )
        logger.info("Created Discord adapter (single bot, legacy mode)")

    return adapters


def _create_discord_adapter(
    config: GatewayConfig, gateway: ChatGateway | None
) -> PlatformAdapter:
    """Create a single Discord adapter (legacy)."""
    if not config.discord_token:
        raise RuntimeError(
            "Discord adapter requested but DISCORD_LLM_BOT_TOKEN is not set"
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
        agent_url=config.march7_url,
    )


def _create_zalo_adapter(config: GatewayConfig) -> PlatformAdapter:
    from gateway.adapters.zalo.adapter import ZaloPlatformAdapter

    if not config.zalo_access_token:
        logger.warning("Zalo adapter requested but ZALO_ACCESS_TOKEN is not set")

    return ZaloPlatformAdapter(
        access_token=config.zalo_access_token,
        app_id=config.zalo_app_id,
    )
