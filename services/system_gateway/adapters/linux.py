"""Linux capability reporting."""
from __future__ import annotations

from .base import CapabilityAdapter, PlatformCapabilities


class LinuxCapabilityAdapter(CapabilityAdapter):
    """Report Linux capabilities.

    The gateway exposes one generic shell-exec path backed by ``/bin/sh``. The
    owner approves the exact command; this adapter just reports the shell and
    lets :meth:`CapabilityAdapter.run_shell` spawn it.
    """

    def capabilities(self) -> PlatformCapabilities:
        return PlatformCapabilities(
            platform="linux",
            shells=["/bin/sh"],
            raw_shell=True,
            features=["generic_shell_exec"],
            notes=[
                "Generic shell execution via /bin/sh. Owner approval gates every command.",
            ],
        )