"""Platform capability adapters."""

from .base import CapabilityAction, CapabilityAdapter, PlatformCapabilities
from .linux import LinuxCapabilityAdapter
from .macos import MacOSCapabilityAdapter
from .windows import WindowsCapabilityAdapter

__all__ = [
    "CapabilityAction",
    "CapabilityAdapter",
    "LinuxCapabilityAdapter",
    "MacOSCapabilityAdapter",
    "PlatformCapabilities",
    "WindowsCapabilityAdapter",
]

