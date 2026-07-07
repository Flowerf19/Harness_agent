"""Evernight-side System Gateway installer/update flow.

This module is the owner-facing orchestration layer for first-run bootstrap
and post-bootstrap updates. The native service lives on the host and is outside
Docker. Evernight:

1. Detects when the native service is missing or outdated.
2. Emits a one-time bootstrap hint or runs the fixed bootstrap command through
   a narrow owner-approved legacy bridge when the gateway is absent on a
   supported platform.
3. When the gateway is present and the owner approves an update, calls a
   restricted ``POST /self/update`` endpoint on the gateway to ask the
   service to update and restart itself.

Owner approval is intentionally required at every step. The first-run
bootstrap bridge is deliberately narrow and must not accept model-generated
shell fragments.
"""
from __future__ import annotations

import logging
import json as jsonlib
import platform
import shlex
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)


# Stable sentinel — GatewayMonitor.compare_versions can compare against this
# to detect "newer than what we know about" without needing a real registry.
KNOWN_GOOD_VERSIONS = ("0.1.0",)

_BOOTSTRAP_ENV_PARSER = r"""
import os
import shlex
import sys
from pathlib import Path

env_path = Path(sys.argv[1])
secret_path = Path(sys.argv[2])
safe_env_path = Path(sys.argv[3])
keys = {"SYSTEM_GATEWAY_SHARED_SECRET", "SYSTEM_GATEWAY_HOST", "SYSTEM_GATEWAY_PORT"}
values = {}

if not env_path.exists():
    raise SystemExit(".env not found")

for raw in env_path.read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#"):
        continue
    if line.startswith("export "):
        line = line[7:].strip()
    key, sep, value = line.partition("=")
    key = key.strip()
    if sep != "=" or key not in keys:
        continue
    try:
        parsed = shlex.split(value, comments=False, posix=True)
    except ValueError as exc:
        raise SystemExit(f"invalid .env value for {key}: {exc}")
    values[key] = parsed[0] if parsed else ""

secret = values.get("SYSTEM_GATEWAY_SHARED_SECRET", "")
if not secret:
    raise SystemExit("SYSTEM_GATEWAY_SHARED_SECRET missing in .env")

host = values.get("SYSTEM_GATEWAY_HOST", "")
if host and any(ch.isspace() for ch in host):
    raise SystemExit("SYSTEM_GATEWAY_HOST must not contain whitespace")

port = values.get("SYSTEM_GATEWAY_PORT", "")
if port:
    try:
        port_int = int(port)
    except ValueError:
        raise SystemExit("SYSTEM_GATEWAY_PORT must be numeric")
    if port_int < 1 or port_int > 65535:
        raise SystemExit("SYSTEM_GATEWAY_PORT must be between 1 and 65535")

secret_path.parent.mkdir(parents=True, exist_ok=True)
try:
    os.chmod(secret_path.parent, 0o700)
except OSError:
    pass
secret_path.write_text(secret, encoding="utf-8")
try:
    os.chmod(secret_path, 0o600)
except OSError:
    pass

exports = []
if host:
    exports.append(f"export SYSTEM_GATEWAY_HOST={shlex.quote(host)}")
if port:
    exports.append(f"export SYSTEM_GATEWAY_PORT={shlex.quote(port)}")
safe_env_path.write_text("\n".join(exports) + "\n", encoding="utf-8")
try:
    os.chmod(safe_env_path, 0o600)
except OSError:
    pass
"""


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


@dataclass(frozen=True)
class BootstrapInstallResult:
    """Result returned by the legacy bootstrap bridge."""

    ok: bool
    message: str
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None


class LegacyBashExecutorBootstrapBridge:
    """Narrow bridge for first-install bootstrap through legacy bash-executor.

    This is intentionally not a general shell runner. The command is generated
    by code, has no model/user supplied shell fragments, and exists only to
    cross the bootstrap gap before the native System Gateway is running.
    """

    def __init__(
        self,
        *,
        executor_url: str,
        repo_root: str,
        python_executable: str,
        venv_path: str = "/opt/system-gateway/venv",
        timeout: int = 120,
    ) -> None:
        self.executor_url = executor_url.rstrip("/")
        self.repo_root = repo_root
        self.python_executable = python_executable
        self.venv_path = venv_path
        self.timeout = max(30, min(300, timeout))

    def build_install_command(self) -> str:
        """Return the fixed host-side bootstrap command."""

        repo_root = shlex.quote(self.repo_root)
        python_executable = shlex.quote(self.python_executable)
        venv_path = shlex.quote(self.venv_path)
        venv_parent = shlex.quote(str(PurePosixPath(self.venv_path).parent))
        return "\n".join(
            [
                "set -euo pipefail",
                f"cd {repo_root}",
                "install -d -m 700 /etc/system-gateway",
                "umask 077",
                f"{python_executable} - ./.env /etc/system-gateway/secret /tmp/system-gateway-bootstrap.env <<'PY'",
                _BOOTSTRAP_ENV_PARSER.strip(),
                "PY",
                "set -a",
                ". /tmp/system-gateway-bootstrap.env",
                "set +a",
                "rm -f /tmp/system-gateway-bootstrap.env",
                f"install -d -m 755 {venv_parent}",
                f"{python_executable} -m venv --system-site-packages {venv_path}",
                f"{venv_path}/bin/python -m pip install --no-build-isolation services/system_gateway",
                (
                    'SYSTEM_GATEWAY_HOST="${SYSTEM_GATEWAY_HOST:-0.0.0.0}" '
                    'SYSTEM_GATEWAY_PORT="${SYSTEM_GATEWAY_PORT:-8380}" '
                    "SYSTEM_GATEWAY_SHARED_SECRET_FILE=/etc/system-gateway/secret "
                    f"{venv_path}/bin/python -m system_gateway install"
                ),
                "systemctl restart system-gateway",
                "for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do",
                '  if curl -sf "http://127.0.0.1:${SYSTEM_GATEWAY_PORT:-8380}/health"; then',
                "    exit 0",
                "  fi",
                "  sleep 1",
                "done",
                "echo 'system-gateway health check failed after restart' >&2",
                "exit 7",
            ]
        )

    async def install(self) -> BootstrapInstallResult:
        """Run the fixed install command through legacy bash-executor."""

        command = self.build_install_command()
        payload = {"command": command, "timeout": self.timeout}
        url = f"{self.executor_url}/execute"
        timeout = aiohttp.ClientTimeout(total=self.timeout + 10)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    url,
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Origin": "march7-bot",
                    },
                ) as resp:
                    data = await resp.json()
                    if resp.status >= 400:
                        return BootstrapInstallResult(
                            ok=False,
                            message=str(data.get("error") or f"HTTP {resp.status}"),
                            stdout=str(data.get("stdout") or ""),
                            stderr=str(data.get("stderr") or ""),
                            exit_code=_optional_int(data.get("exit_code")),
                        )
        except aiohttp.ClientError as exc:
            return BootstrapInstallResult(
                ok=False,
                message=f"bootstrap executor unreachable: {exc}",
            )

        if data.get("error"):
            return BootstrapInstallResult(
                ok=False,
                message=str(data.get("error")),
                stdout=str(data.get("stdout") or ""),
                stderr=str(data.get("stderr") or ""),
                exit_code=_optional_int(data.get("exit_code")),
            )

        exit_code = _optional_int(data.get("exit_code"))
        ok = exit_code == 0
        return BootstrapInstallResult(
            ok=ok,
            message="system-gateway bootstrap completed" if ok else "bootstrap command failed",
            stdout=str(data.get("stdout") or ""),
            stderr=str(data.get("stderr") or ""),
            exit_code=exit_code,
        )


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


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
