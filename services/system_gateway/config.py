"""Runtime configuration for the System Gateway scaffold."""
from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class GatewayConfig:
    """Small configuration object for the native service."""

    host: str = "127.0.0.1"
    # Port 8380 matches SYSTEM_GATEWAY_URL in twin/shared/config/settings.py and
    # the SYSTEM_GATEWAY_URL wired into the march7/evernight containers.
    port: int = 8380
    raw_shell_enabled: bool = False
    shared_secret: str | None = None

    @classmethod
    def from_env(cls) -> GatewayConfig:
        """Load config from environment variables."""

        shared_secret = os.getenv("SYSTEM_GATEWAY_SHARED_SECRET") or None
        secret_file = os.getenv("SYSTEM_GATEWAY_SHARED_SECRET_FILE")
        if not shared_secret and secret_file:
            shared_secret = _read_secret_file(secret_file)

        return cls(
            host=os.getenv("SYSTEM_GATEWAY_HOST", cls.host),
            port=_parse_port(os.getenv("SYSTEM_GATEWAY_PORT"), cls.port),
            raw_shell_enabled=_parse_bool(
                os.getenv("SYSTEM_GATEWAY_RAW_SHELL"), cls.raw_shell_enabled
            ),
            shared_secret=shared_secret,
        )


def _parse_port(raw_port: str | None, default: int) -> int:
    if raw_port is None or raw_port == "":
        return default
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise ValueError("SYSTEM_GATEWAY_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise ValueError("SYSTEM_GATEWAY_PORT must be between 1 and 65535")
    return port


def _read_secret_file(path: str) -> str | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip() or None
    except FileNotFoundError:
        return None


def _parse_bool(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}
