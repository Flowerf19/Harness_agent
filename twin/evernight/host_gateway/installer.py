"""Evernight-side Host Gateway installer/update flow.

This module is the owner-facing orchestration layer for first-run bootstrap
and post-bootstrap updates. The native service lives on the host and is outside
Docker. Evernight:

1. Detects when the native service is missing or outdated.
2. Emits a one-time owner-facing bootstrap hint when the gateway is absent.
3. When the gateway is present and the owner approves an update, calls a
   restricted ``POST /self/update`` endpoint on the gateway to ask the
   service to update and restart itself.

Owner approval is intentionally required for gateway actions with side effects.
"""
from __future__ import annotations

import os
import logging
import json as jsonlib
import shlex
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)


# Stable sentinel — GatewayMonitor.compare_versions can compare against this
# to detect "newer than what we know about" without needing a real registry.
KNOWN_GOOD_VERSIONS = ("0.1.0",)
BOOTSTRAP_REPO_PLACEHOLDER = "/path/to/march7"
BOOTSTRAP_SCRIPT_REL = "scripts/bootstrap_system_gateway.py"
_BOOTSTRAP_SCRIPT_SUFFIXES = (
    f"/{BOOTSTRAP_SCRIPT_REL}",
    "\\scripts\\bootstrap_system_gateway.py",
)


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
            f"**System Gateway install** (`{self.platform}`):",
            "```sh",
            self.command,
            "```",
        ]
        if self.notes:
            lines.extend(self.notes)
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


def _normalise_owner_repo_root(repo_root: str) -> str:
    """Accept either repo root or the bootstrap script path from the owner."""

    value = repo_root.strip().strip("\"'")
    trimmed = value.rstrip("/\\")
    lowered = trimmed.lower()
    for suffix in _BOOTSTRAP_SCRIPT_SUFFIXES:
        if lowered.endswith(suffix.lower()):
            return str(Path(trimmed[: -len(suffix)]).expanduser())
    for suffix in ("/scripts", "\\scripts"):
        if lowered.endswith(suffix):
            return str(Path(trimmed[: -len(suffix)]).expanduser())
    return str(Path(value).expanduser())


def _quote_windows_cmd_arg(value: str) -> str:
    unsafe = {'"', "\r", "\n", "\x00", "%", "!"}
    if any(ch in value for ch in unsafe):
        raise ValueError("Unsafe Windows install_path for cmd.exe command")
    return f'"{value}"'


def _resolve_repo_root(install_path: str | None = None) -> tuple[str, str]:
    if install_path and install_path.strip():
        return _normalise_owner_repo_root(install_path), "owner"

    repo_root = os.getenv("SYSTEM_GATEWAY_BOOTSTRAP_REPO_ROOT")
    if not repo_root:
        return BOOTSTRAP_REPO_PLACEHOLDER, "placeholder"

    root = Path(repo_root).expanduser()
    markers = (
        root / BOOTSTRAP_SCRIPT_REL,
        root / "services" / "system_gateway",
    )
    if all(marker.exists() for marker in markers):
        return str(root), "verified"
    return BOOTSTRAP_REPO_PLACEHOLDER, "placeholder"


def build_bootstrap_hint(
    platform_name: Optional[str] = None,
    *,
    install_path: str | None = None,
    repo_root: str | None = None,
) -> BootstrapHint:
    """Return the bootstrap command for the given platform.

    The exact commands are intentionally simple and explicit so the owner can
    copy/paste them on the host. No agent-side legacy executor is used.
    """

    name = platform_name or _detect_platform()
    repo_root, repo_source = _resolve_repo_root(install_path or repo_root)
    repo_note = {
        "owner": "Path cài đặt owner cung cấp; script tự biết phần còn lại.",
        "verified": "Repo root đã verify; chạy lệnh trên host.",
        "placeholder": (
            "Đổi `/path/to/march7` thành thư mục cài March7 trên host; "
            "script tự biết phần còn lại."
        ),
    }[repo_source]
    if name == "linux":
        return BootstrapHint(
            platform=name,
            command=(
                f"cd {shlex.quote(repo_root)} "
                f"&& python3 {shlex.quote(BOOTSTRAP_SCRIPT_REL)}"
            ),
            notes=(
                repo_note,
            ),
        )
    if name == "macos":
        return BootstrapHint(
            platform=name,
            command=(
                f"cd {shlex.quote(repo_root)} "
                f"&& python3 {shlex.quote(BOOTSTRAP_SCRIPT_REL)}"
            ),
            notes=(
                repo_note,
            ),
        )
    if name == "windows":
        return BootstrapHint(
            platform=name,
            command=(
                f"cd /d {_quote_windows_cmd_arg(repo_root)} "
                "&& python scripts\\bootstrap_system_gateway.py"
            ),
            notes=(
                repo_note,
                "Windows: chạy trong Administrator shell.",
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
    shared_secret: str | None = None
    actor: str = "evernight"

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
        verifies ``approval_id`` is fresh, non-replayed, and action-bound.
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
        if not self.shared_secret:
            return False, "shared secret missing; cannot sign update request"
        from twin.shared.system_gateway.auth import headers_from_signed, sign_request

        body_bytes = jsonlib.dumps(payload, separators=(",", ":")).encode("utf-8")
        signed = sign_request(
            secret=self.shared_secret,
            method="POST",
            path="/self/update",
            actor=self.actor,
            body=body_bytes,
        )
        headers = {"Content-Type": "application/json"}
        headers.update(headers_from_signed(signed))
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, data=body_bytes, headers=headers) as resp:
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
