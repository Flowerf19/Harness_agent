"""System Gateway client errors."""
from __future__ import annotations


class HostGatewayError(Exception):
    """Base error for System Gateway communication failures."""


class HostGatewayUnavailableError(HostGatewayError):
    """Raised when the native System Gateway service is not reachable."""
