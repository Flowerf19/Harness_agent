"""Evernight-side System Gateway installer/update flow.

This module is the owner-facing orchestration layer for first-run bootstrap
and post-bootstrap updates. It does NOT install or update the gateway itself;
the native service lives on the host and is outside Docker. Instead Evernight:

1. Detects when the native service is missing or outdated.
2. Emits a one-time bootstrap hint (the exact command the owner must run on
   the host) when the gateway is absent on a supported platform.
3. When the gateway is present and the owner approves an update, calls a
   restricted ``POST /self/update`` endpoint on the gateway to ask the
   service to update and restart itself.

Owner approval is intentionally required at every step. The first-run
bootstrap command is the only piece Evernight cannot automate without a
pre-existing OS management credential.
"""
from __future__ import annotations

import logging
import platform
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)


# Stable sentinel — GatewayMonitor.compare_versions can compare against this
# to detect "newer than what we know about" without needing a real registry.
KNOWN_GOOD_VERSIONS = ("0.1.0",)


class InstallerAction(str, Enum):
    """Action the owner can request through Evernight."""

    INSTALL = "install"
    UPDATE = "update"
    UNINSTALL = "uninstall"


@dataclass(frozen=True)
class BootstrapHint:
    """The exact command the owner must run on the host."""

    platform: str
    command: str
    notes: tuple[str, ...] = ()

    def render_for_chat(self) -> str:
        lines = [
            f"📦 **System Gateway bootstrap** (`{self.platform}`):",
            "```",
            self.command,
            "```",
        ]
        if self.notes:
            lines.append("\n".join(f"- {n}" for n in self.notes))
        return "\n".join(lines)


def _detect_platform() -> str:
    """Return a coarse platform id used to pick a bootstrap hint."""

    name = sys_platform() or "unknown"
    if name.startswith("linux"):
        return "linux"
    if name == "darwin":
        return "macos"
    if name.startswith(("win32", "cygwin", "msys")):
        return "windows"
    return name


def sys_platform() -> str:
    import sys

    return sys.platform


def build_bootstrap_hint(platform_name: Optional[str] = None) -> BootstrapHint:
    """Return the bootstrap command for the given platform.

    The exact commands are intentionally simple and explicit so the owner can
    copy/paste them. They assume the ``system-gateway`` package is installed
    in a virtualenv on the host.
    """

    name = platform_name or _detect_platform()
    if name == "linux":
        return BootstrapHint(
            platform=name,
            command=(
                "sudo tee /etc/systemd/system/system-gateway.service >/dev/null "
                "<<'UNIT'\n[Unit]\nDescription=System Gateway\nAfter=network-online.target\n\n"
                "[Service]\nType=simple\nExecStart=/usr/local/bin/system-gateway\n"
                "Restart=on-failure\nUNIT\n"
                "sudo systemctl daemon-reload && sudo systemctl enable --now system-gateway"
            ),
            notes=(
                "Yêu cầu file service trong services/system_gateway/packaging/linux/.",
                "Sau khi service chạy, kiểm tra `curl http://127.0.0.1:8765/health`.",
            ),
        )
    if name == "macos":
        return BootstrapHint(
            platform=name,
            command=(
                "cp services/system_gateway/packaging/macos/com.twin.system-gateway.plist "
                "~/Library/LaunchAgents/ && launchctl load -w "
                "~/Library/LaunchAgents/com.twin.system-gateway.plist"
            ),
            notes=(
                "Yêu cầu `system-gateway` đã được `pip install` vào user env.",
            ),
        )
    if name == "windows":
        return BootstrapHint(
            platform=name,
            command=(
                "python -m pip install -e services\\system_gateway && "
                "python -m system_gateway"
            ),
            notes=(
                "Windows packaging notes ở services/system_gateway/packaging/windows/README.md.",
                "Background service registration chưa được implement — chạy foreground.",
            ),
        )
    return BootstrapHint(
        platform=name,
        command="echo 'No bootstrap command for this platform yet.'",
        notes=(
            f"Platform {name!r} không có sẵn bootstrap command.",
            "Cập nhật services/system_gateway/packaging/ cho platform này.",
        ),
    )


@dataclass
class InstallerCoordinator:
    """Owns the install/update handshake with the native gateway.

    The coordinator is intentionally side-effect free until the owner approves
    an action. Methods return what *would* happen or what *did* happen
    according to the gateway's response.
    """

    base_url: str
    timeout: int = 10
    expected_version: Optional[str] = KNOWN_GOOD_VERSIONS[-1]

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")

    def status_summary(self, current_version: Optional[str]) -> str:
        """Return an owner-facing line describing the install state."""

        if current_version is None:
            return (
                "❌ **System Gateway chưa cài đặt.** Chạy bootstrap command dưới đây:"
            )
        if self.expected_version and current_version != self.expected_version:
            return (
                f"⚠️ Gateway version `{current_version}` "
                f"khác expected `{self.expected_version}`. "
                "Có thể cần `update` (cần owner approval)."
            )
        return f"✅ Gateway version `{current_version}` up-to-date."

    async def request_update(
        self,
        current_version: Optional[str],
        *,
        approval_id: Optional[str] = None,
        target_version: Optional[str] = None,
    ) -> tuple[bool, str]:
        """Ask the gateway to update itself through its restricted endpoint.

        The native service must expose ``POST /self/update``. The handler
        verifies ``approval_id`` is fresh and non-replayed, matching the same
        approval semantics used by ``/actions/run``.
        """

        if current_version is None:
            return False, "gateway missing; use install/bootstrap first"
        payload: dict[str, object] = {
            "from_version": current_version,
        }
        if target_version:
            payload["to_version"] = target_version
        if approval_id:
            payload["approval_id"] = approval_id

        url = f"{self.base_url}/self/update"
        timeout = aiohttp.ClientTimeout(total=self.timeout + 5)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status >= 400:
                        return False, f"HTTP {resp.status}"
                    data = await resp.json()
        except aiohttp.ClientError as exc:
            return False, f"gateway unreachable: {exc}"

        ok = bool(data.get("ok"))
        return ok, data.get("message") or data.get("error") or "no message"

    def render_bootstrap_hint(self, platform_name: Optional[str] = None) -> str:
        return build_bootstrap_hint(platform_name).render_for_chat()


def compare_versions(left: str, right: str) -> int:
    """Return -1/0/1 if left is older/equal/newer than right."""

    def parts(v: str) -> tuple[int, ...]:
        return tuple(int(segment) for segment in v.split(".") if segment.isdigit())

    l, r = parts(left), parts(right)
    if l < r:
        return -1
    if l > r:
        return 1
    return 0
