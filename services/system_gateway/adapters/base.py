"""Capability adapter contracts for host platforms."""

from __future__ import annotations

import asyncio
import os
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

    Shared helper so subprocess actions can reuse the same timeout guard.
    Raises ``asyncio.TimeoutError`` when the deadline is exceeded.
    """

    return await asyncio.wait_for(factory(), timeout=timeout)


@dataclass(frozen=True)
class PlatformCapabilities:
    """Reported capabilities for one host platform.

    The gateway exposes one generic shell-exec path; the adapter's only job is to
    report which OS shell to use. There are no per-action scaffolds — adding a
    host "feature" is just a different command the owner approves.
    """

    platform: str
    shells: list[str] = field(default_factory=list)
    raw_shell: bool = False
    features: list[str] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "shells": list(self.shells),
            "raw_shell": self.raw_shell,
            "features": list(self.features),
            # Kept empty for client-parse compatibility; the generic-shell model
            # has no structured actions.
            "structured_actions": [],
            "action_details": [],
            "unsupported": list(self.unsupported),
            "notes": list(self.notes),
        }


class CapabilityAdapter(ABC):
    """Base class for platform-specific capability reporters."""

    @abstractmethod
    def capabilities(self) -> PlatformCapabilities:
        """Return honest capabilities for the current adapter."""

    async def run_shell(
        self,
        command: str,
        *,
        shell: str | None = None,
        cwd: str | None = None,
        timeout: int = 30,
        max_output_chars: int = 8000,
    ) -> dict[str, Any]:
        """Execute *command* on the adapter's OS shell.

        OS-agnostic: the interpreter comes from ``shell`` (caller override) or
        ``capabilities().shells[0]``. Argv is built via :meth:`_shell_argv`.
        Returns ``{ok, output, error, exit_code, data}``. The owner-approved
        command is run verbatim — no argument validation here, because the
        whole command is the thing the owner saw and approved.
        """

        interpreter = shell or (self.capabilities().shells[0:1] or [""])[0]
        if not interpreter:
            return {
                "ok": False,
                "output": "",
                "error": "no_shell_available",
                "exit_code": None,
                "data": {},
            }

        argv = self._shell_argv(interpreter, command)
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd or None,
            )
        except FileNotFoundError:
            return {
                "ok": False,
                "output": "",
                "error": f"shell_not_found:{interpreter}",
                "exit_code": 127,
                "data": {"shell": interpreter},
            }
        except NotADirectoryError as exc:
            return {
                "ok": False,
                "output": "",
                "error": "invalid_cwd",
                "exit_code": None,
                "data": {"cwd": cwd, "reason": str(exc)},
            }

        try:
            stdout_bytes, stderr_bytes = await run_with_timeout(
                lambda: proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {
                "ok": False,
                "output": "",
                "error": "timed_out",
                "exit_code": -1,
                "data": {"shell": interpreter, "timeout": timeout},
            }

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        return {
            "ok": proc.returncode == 0,
            "output": truncate_output(stdout or stderr, max_output_chars),
            "error": None if proc.returncode == 0 else "command_failed",
            "exit_code": proc.returncode,
            "data": {"shell": interpreter, "command": command},
        }

    @staticmethod
    def _shell_argv(interpreter: str, command: str) -> list[str]:
        """Build the argv for spawning *interpreter* on *command*.

        PowerShell takes ``-NoProfile -Command <command>``; POSIX-style shells
        take ``-c <command>``.
        """

        base = os.path.basename(interpreter).lower()
        if "powershell" in base or base.endswith(".ps1"):
            return [interpreter, "-NoProfile", "-Command", command]
        return [interpreter, "-c", command]


class UnsupportedCapabilityAdapter(CapabilityAdapter):
    """Report that the current platform has no implemented adapter."""

    def __init__(self, platform: str) -> None:
        self._platform = platform

    def capabilities(self) -> PlatformCapabilities:
        return PlatformCapabilities(
            platform=self._platform,
            features=["read_only_capability_report", "unsupported_platform"],
            unsupported=["shell"],
            notes=[
                "No adapter is implemented for this platform.",
                "No subprocess execution is implemented.",
            ],
        )