"""macOS capability reporting."""

from __future__ import annotations

from .base import CapabilityAdapter, PlatformCapabilities


class MacOSCapabilityAdapter(CapabilityAdapter):
    """Report macOS capabilities.

    Generic shell execution via ``/bin/zsh``; inherits :meth:`run_shell` from the
    base. Untested on this Linux host but functional by construction.
    """

    def capabilities(self) -> PlatformCapabilities:
        return PlatformCapabilities(
            platform="macos",
            shells=["/bin/zsh"],
            raw_shell=True,
            features=["generic_shell_exec"],
            notes=[
                "Generic shell execution via /bin/zsh. Owner approval gates every command.",
            ],
        )