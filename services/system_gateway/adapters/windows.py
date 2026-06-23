"""Windows capability reporting."""

from __future__ import annotations

from .base import CapabilityAction, CapabilityAdapter, PlatformCapabilities


class WindowsCapabilityAdapter(CapabilityAdapter):
    """Report Windows scaffold capabilities without executing commands."""

    def capabilities(self) -> PlatformCapabilities:
        return PlatformCapabilities(
            platform="windows",
            shells=["powershell.exe"],
            raw_shell=False,
            features=[
                "read_only_capability_report",
                "stub_adapter",
            ],
            actions=[
                CapabilityAction(
                    name="system.status",
                    description="Read host platform metadata.",
                    available=False,
                ),
            ],
            unsupported=["raw_shell", "structured_actions"],
            notes=[
                "Stub adapter only; no host operations are implemented.",
                "No subprocess execution is implemented.",
            ],
        )
