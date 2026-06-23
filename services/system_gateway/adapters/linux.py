"""Linux capability reporting."""

from __future__ import annotations

from .base import CapabilityAction, CapabilityAdapter, PlatformCapabilities


class LinuxCapabilityAdapter(CapabilityAdapter):
    """Report read-only Linux capabilities without executing commands."""

    def capabilities(self) -> PlatformCapabilities:
        return PlatformCapabilities(
            platform="linux",
            shells=["/bin/sh"],
            raw_shell=False,
            features=[
                "read_only_capability_report",
                "structured_actions_only",
            ],
            actions=[
                CapabilityAction(
                    name="system.status",
                    description="Read host platform metadata.",
                    available=False,
                ),
                CapabilityAction(
                    name="system.disk_usage",
                    description="Read disk usage when policy support exists.",
                    available=False,
                ),
                CapabilityAction(
                    name="docker.list_containers",
                    description="List Docker containers when policy support exists.",
                    available=False,
                ),
            ],
            unsupported=["raw_shell"],
            notes=[
                "No subprocess execution is implemented.",
                "Only capability metadata is exposed by this scaffold.",
            ],
        )
