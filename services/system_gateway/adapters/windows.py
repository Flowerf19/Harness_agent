"""Windows capability reporting."""

from __future__ import annotations

from .base import CapabilityAdapter, PlatformCapabilities


class WindowsCapabilityAdapter(CapabilityAdapter):
    """Report Windows capabilities.

    Generic shell execution via ``powershell.exe``; inherits :meth:`run_shell`
    from the base. Untested on this Linux host but functional by construction.
    """

    def capabilities(self) -> PlatformCapabilities:
        return PlatformCapabilities(
            platform="windows",
            shells=["powershell.exe"],
            raw_shell=True,
            features=["generic_shell_exec"],
            notes=[
                "Generic shell execution via powershell.exe. Owner approval gates every command.",
            ],
        )