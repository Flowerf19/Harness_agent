"""Platform capability adapters."""

from .base import CapabilityAdapter, PlatformCapabilities
from .linux import LinuxCapabilityAdapter
from .macos import MacOSCapabilityAdapter
from .windows import WindowsCapabilityAdapter

__all__ = [
    "CapabilityAdapter",
    "LinuxCapabilityAdapter",
    "MacOSCapabilityAdapter",
    "PlatformCapabilities",
    "WindowsCapabilityAdapter",
]