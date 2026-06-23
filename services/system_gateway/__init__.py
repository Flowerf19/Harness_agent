"""System Gateway native service scaffold."""

from .config import GatewayConfig
from .server import create_app

__all__ = ["GatewayConfig", "create_app"]

