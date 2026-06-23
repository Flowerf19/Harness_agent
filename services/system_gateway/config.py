"""Runtime configuration for the System Gateway scaffold."""

from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class GatewayConfig:
    """Small configuration object for the native service."""

    host: str = "127.0.0.1"
    port: int = 8765

    @classmethod
    def from_env(cls) -> GatewayConfig:
        """Load config from environment variables."""

        return cls(
            host=os.getenv("SYSTEM_GATEWAY_HOST", cls.host),
            port=_parse_port(os.getenv("SYSTEM_GATEWAY_PORT"), cls.port),
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

