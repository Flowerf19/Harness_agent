"""Gateway configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class GatewayConfig:
    """Top-level configuration for the multi-platform gateway."""

    # Which platform adapters to load at startup.
    enabled_platforms: list[str] = field(default_factory=lambda: ["discord"])

    # Per-platform config dicts — populated from env vars.
    discord_token: str = ""
    discord_enabled: bool = True

    discord_march7_token: str = ""
    discord_evernight_token: str = ""

    zalo_access_token: str = ""
    zalo_app_id: str = ""
    zalo_enabled: bool = False

    @classmethod
    def from_env(cls) -> "GatewayConfig":
        """Read configuration from ``os.environ``."""
        enabled_raw = os.getenv("GATEWAY_ENABLED_PLATFORMS", "discord")
        enabled_platforms = [p.strip() for p in enabled_raw.split(",") if p.strip()]

        discord_enabled_env = os.getenv("DISCORD_GATEWAY_ENABLED", "true").lower()
        discord_enabled = discord_enabled_env in ("1", "true", "yes")

        discord_token = os.getenv("DISCORD_MARCH7_TOKEN", "")
        discord_march7_token = os.getenv("DISCORD_MARCH7_TOKEN", "")
        discord_evernight_token = os.getenv("DISCORD_EVERNIGHT_TOKEN", "")

        zalo_enabled_env = os.getenv("ZALO_ENABLED", "false").lower()
        zalo_enabled = zalo_enabled_env in ("1", "true", "yes")

        return cls(
            enabled_platforms=enabled_platforms,
            discord_token=discord_token,
            discord_enabled=discord_enabled,
            discord_march7_token=discord_march7_token,
            discord_evernight_token=discord_evernight_token,
            zalo_access_token=os.getenv("ZALO_ACCESS_TOKEN", ""),
            zalo_app_id=os.getenv("ZALO_APP_ID", ""),
            zalo_enabled=zalo_enabled,
        )

    def platform_enabled(self, name: str) -> bool:
        """Return ``True`` if platform *name* is enabled."""
        return name.lower() in [p.lower() for p in self.enabled_platforms]
