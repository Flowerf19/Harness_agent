"""Capability adapter contracts for host platforms."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, TypeVar

_T = TypeVar("_T")


def truncate_output(text: str, max_output_chars: int) -> str:
    """Truncate output to at most ``max_output_chars`` with a marker suffix."""

    if max_output_chars <= 0 or len(text) <= max_output_chars:
        return text
    return f"{text[:max_output_chars]}\n... [truncated: {len(text)} chars total]"


async def run_with_timeout(
    factory: Callable[[], Awaitable[_T]],
    *,
    timeout: int,
) -> _T:
    """Run a coroutine under ``asyncio.wait_for`` with the given timeout.

    Shared helper so Phase 2 subprocess actions can reuse the same timeout
    guard. Raises ``asyncio.TimeoutError`` when the deadline is exceeded.
    """

    return await asyncio.wait_for(factory(), timeout=timeout)


@dataclass(frozen=True)
class CapabilityAction:
    """A structured action name that may be supported by a platform adapter."""

    name: str
    description: str
    read_only: bool = True
    available: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "read_only": self.read_only,
            "available": self.available,
        }


@dataclass(frozen=True)
class PlatformCapabilities:
    """Reported capabilities for one host platform."""

    platform: str
    shells: list[str] = field(default_factory=list)
    raw_shell: bool = False
    features: list[str] = field(default_factory=list)
    actions: list[CapabilityAction] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "shells": list(self.shells),
            "raw_shell": self.raw_shell,
            "features": list(self.features),
            "structured_actions": [
                action.name
                for action in self.actions
                if action.available and action.read_only
            ],
            "action_details": [action.to_dict() for action in self.actions],
            "unsupported": list(self.unsupported),
            "notes": list(self.notes),
        }


class CapabilityAdapter(ABC):
    """Base class for platform-specific capability reporters."""

    @abstractmethod
    def capabilities(self) -> PlatformCapabilities:
        """Return honest capabilities for the current adapter."""

    async def run_action(
        self,
        action: str,
        arguments: dict[str, Any],
        *,
        timeout: int,
        max_output_chars: int,
    ) -> dict[str, Any]:
        """Execute a structured action.

        Returns a dict shaped like ``GatewayActionResponse``:
        ``{ok, output, error, exit_code, data}``. The default implementation
        reports that the action is not supported; platform adapters override
        this for the actions they implement.
        """

        return {
            "ok": False,
            "output": "",
            "error": "action_not_supported",
            "exit_code": None,
            "data": {},
        }


class UnsupportedCapabilityAdapter(CapabilityAdapter):
    """Report that the current platform has no implemented adapter."""

    def __init__(self, platform: str) -> None:
        self._platform = platform

    def capabilities(self) -> PlatformCapabilities:
        return PlatformCapabilities(
            platform=self._platform,
            features=["read_only_capability_report", "unsupported_platform"],
            actions=[],
            unsupported=["shell", "structured_actions"],
            notes=[
                "No adapter is implemented for this platform.",
                "No subprocess execution is implemented.",
            ],
        )
