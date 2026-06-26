"""System Gateway native service scaffold."""

from .config import GatewayConfig
from .server import create_app
from .state import SERVICE_VERSION, GatewayState

__all__ = ["GatewayConfig", "GatewayState", "SERVICE_VERSION", "create_app"]
