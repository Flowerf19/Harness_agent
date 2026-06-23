"""Shared client/protocol types for the native System Gateway."""
from twin.shared.system_gateway.client import HostGatewayClient
from twin.shared.system_gateway.errors import (
    HostGatewayError,
    HostGatewayUnavailableError,
)
from twin.shared.system_gateway.types import (
    GatewayActionRequest,
    GatewayActionResponse,
    GatewayCapabilities,
    GatewayHealth,
    GatewayShellRequest,
)

__all__ = [
    "GatewayActionRequest",
    "GatewayActionResponse",
    "GatewayCapabilities",
    "GatewayHealth",
    "GatewayShellRequest",
    "HostGatewayClient",
    "HostGatewayError",
    "HostGatewayUnavailableError",
]
