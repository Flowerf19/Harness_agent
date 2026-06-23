"""Capability selection for the native System Gateway service."""

from __future__ import annotations

import sys

from .adapters.base import (
    CapabilityAdapter,
    PlatformCapabilities,
    UnsupportedCapabilityAdapter,
)
from .adapters.linux import LinuxCapabilityAdapter
from .adapters.macos import MacOSCapabilityAdapter
from .adapters.windows import WindowsCapabilityAdapter


def select_adapter(platform: str | None = None) -> CapabilityAdapter:
    """Select a capability reporter for a Python platform name."""

    platform_name = platform or sys.platform
    if platform_name.startswith("linux"):
        return LinuxCapabilityAdapter()
    if platform_name == "darwin":
        return MacOSCapabilityAdapter()
    if platform_name.startswith(("win32", "cygwin", "msys")):
        return WindowsCapabilityAdapter()
    return UnsupportedCapabilityAdapter(platform_name)


def get_capabilities(adapter: CapabilityAdapter | None = None) -> PlatformCapabilities:
    """Return capabilities from the selected platform adapter."""

    selected = adapter or select_adapter()
    return selected.capabilities()


def capabilities_payload(adapter: CapabilityAdapter | None = None) -> dict[str, object]:
    """Return the JSON-serializable capabilities response."""

    payload = get_capabilities(adapter).to_dict()
    payload["service"] = "system_gateway"
    return payload
