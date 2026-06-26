"""Command-line interface for the native System Gateway service.

The CLI is the owner-facing control plane on the host. It can:

* run the gateway service (`system-gateway run`, default)
* report local status/capabilities (`status`, `doctor`, `capabilities`)
* stream service logs (`logs`)
* generate and store shared auth material (`pair`)
* install/uninstall the native service (`install`, `uninstall`)
* request an in-place update (`update`)

All mutating commands require the shared secret to be configured via the
``SYSTEM_GATEWAY_SHARED_SECRET`` environment variable (or a secret file).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import secrets
import sys
import urllib.request
from pathlib import Path
from typing import Sequence

from aiohttp import web

from ..config import GatewayConfig
from ..server import create_app
from ..state import SERVICE_VERSION

logger = logging.getLogger(__name__)

DEFAULT_URL = "http://127.0.0.1:8380"


def _default_config_dir() -> Path:
    """Return the host config directory used by ``pair``."""

    if sys.platform.startswith("win"):
        base = os.getenv("LOCALAPPDATA") or os.path.expanduser("~")
        return Path(base) / "system-gateway"
    if sys.platform == "darwin":
        return Path(os.path.expanduser("~")) / "Library" / "Application Support" / "system-gateway"
    return Path("/etc") / "system-gateway"


def _default_secret_file() -> Path:
    return _default_config_dir() / "secret"


def _read_secret_file(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None


def _ensure_secret_file(path: Path, secret: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(secret, encoding="utf-8")
    # Restrict to owner only; best-effort on Windows.
    try:
        os.chmod(path, 0o600)
    except OSError:  # pragma: no cover
        pass


def _http_get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _cmd_status(args: argparse.Namespace) -> int:
    url = (args.url or DEFAULT_URL).rstrip("/")
    try:
        data = _http_get_json(f"{url}/health")
    except Exception as exc:  # pragma: no cover - exercised manually
        print(f"❌ System Gateway unreachable at {url}: {exc}", file=sys.stderr)
        return 1

    print(f"Status: {data.get('status')}")
    print(f"Service: {data.get('service')}")
    print(f"Version: {data.get('version')}")
    print(f"Uptime: {data.get('uptime')}s")
    print(f"Platform: {data.get('platform')}")
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    url = (args.url or DEFAULT_URL).rstrip("/")
    ok = True
    try:
        health = _http_get_json(f"{url}/health")
    except Exception as exc:  # pragma: no cover - exercised manually
        print(f"❌ /health unreachable: {exc}")
        return 1

    print("Health:")
    for key in ("status", "version", "platform", "uptime"):
        print(f"  {key}: {health.get(key)}")

    try:
        caps = _http_get_json(f"{url}/capabilities")
    except Exception as exc:  # pragma: no cover - exercised manually
        print(f"❌ /capabilities unreachable: {exc}")
        return 1

    print("Capabilities:")
    for key in ("platform", "shells", "features", "raw_shell", "structured_actions"):
        print(f"  {key}: {caps.get(key)}")

    if health.get("version") != SERVICE_VERSION:
        print(f"⚠️  Service reports {health.get('version')}; CLI is {SERVICE_VERSION}.")
        ok = False

    secret = os.getenv("SYSTEM_GATEWAY_SHARED_SECRET")
    secret_file = os.getenv("SYSTEM_GATEWAY_SHARED_SECRET_FILE")
    if not secret and not secret_file:
        print("⚠️  No SYSTEM_GATEWAY_SHARED_SECRET or SYSTEM_GATEWAY_SHARED_SECRET_FILE set.")
        print("   Run `system-gateway pair` to provision one.")
        ok = False

    return 0 if ok else 2


def _cmd_capabilities(args: argparse.Namespace) -> int:
    url = (args.url or DEFAULT_URL).rstrip("/")
    try:
        data = _http_get_json(f"{url}/capabilities")
    except Exception as exc:  # pragma: no cover - exercised manually
        print(f"❌ {exc}", file=sys.stderr)
        return 1
    print(json.dumps(data, indent=2))
    return 0


def _cmd_logs(args: argparse.Namespace) -> int:
    """Stream native service logs using the platform's log tool."""

    if sys.platform.startswith("linux"):
        cmd = ["journalctl", "-u", "system-gateway", "-f"]
    elif sys.platform == "darwin":
        cmd = ["log", "stream", "--predicate", 'process == "system-gateway"']
    else:  # pragma: no cover
        print("❌ `logs` is not implemented for this platform.")
        print("   On Windows, use Event Viewer or the console output of the service.")
        return 1

    try:
        os.execvp(cmd[0], cmd)
    except FileNotFoundError as exc:  # pragma: no cover - exercised manually
        print(f"❌ Could not start log viewer: {exc}", file=sys.stderr)
        return 1


def _cmd_pair(args: argparse.Namespace) -> int:
    """Generate and store shared auth material for pairing with a container."""

    config_dir = _default_config_dir()
    secret_file = Path(args.secret_file) if args.secret_file else _default_secret_file()

    existing = _read_secret_file(secret_file)
    if existing and not args.force:
        print(f"⚠️  Secret file already exists at {secret_file}.")
        print("   Use --force to regenerate (this will invalidate existing clients).")
        return 2

    secret = secrets.token_urlsafe(32)
    _ensure_secret_file(secret_file, secret)

    print("🔐 Generated shared secret for System Gateway pairing.")
    print(f"   Stored at: {secret_file}")
    print("   Permissions: owner-read only")
    print()
    print("Add this secret to the agent containers via ONE of these methods:")
    print()
    print("  1. Environment variable on the host that launches the containers:")
    print(f"     export SYSTEM_GATEWAY_SHARED_SECRET={secret}")
    print()
    print(f"  2. Point the service at the file (host path must be readable by service):")
    print(f"     export SYSTEM_GATEWAY_SHARED_SECRET_FILE={secret_file}")
    print()
    print("  3. In container orchestration, set SYSTEM_GATEWAY_SHARED_SECRET from a secret.")
    print()
    print("⚠️  Do not commit this value. Treat it like a password.")

    if not secret_file.parent.exists():
        secret_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    return 0


def _service_file_path(platform: str) -> Path:
    here = Path(__file__).resolve().parent.parent / "packaging"
    if platform == "linux":
        return here / "linux" / "system-gateway.service"
    if platform == "darwin":
        return here / "macos" / "com.twin.system-gateway.plist"
    raise RuntimeError(f"unsupported platform: {platform}")


def _systemd_unit_path() -> Path:
    return Path("/etc/systemd/system/system-gateway.service")


def _launchd_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / "com.twin.system-gateway.plist"


def _is_root() -> bool:
    return os.geteuid() == 0 if hasattr(os, "geteuid") else False


def _cmd_install(args: argparse.Namespace) -> int:
    """Install and start the native service."""

    platform = "darwin" if sys.platform == "darwin" else "linux"
    if platform not in {"linux", "darwin"}:  # pragma: no cover
        print("❌ Native install is only supported on Linux and macOS.")
        print("   On Windows see packaging/windows/README.md for manual setup.")
        return 1

    src = _service_file_path(platform)
    if not src.exists():
        print(f"❌ Packaging file not found: {src}", file=sys.stderr)
        return 1

    # Ensure secret exists before installing; otherwise the service would refuse
    # mutating requests and most admin operations would fail.
    secret_file = _default_secret_file()
    if not secret_file.exists():
        print("🔐 No shared secret found. Generating one first...")
        _cmd_pair(argparse.Namespace(secret_file=str(secret_file), force=False))

    if platform == "linux":
        if not _is_root():
            print("❌ Linux install requires root (systemctl/systemd).", file=sys.stderr)
            return 1
        dst = _systemd_unit_path()
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        _run_or_warn(["systemctl", "daemon-reload"])
        _run_or_warn(["systemctl", "enable", "--now", "system-gateway"])
        print(f"✅ Installed {dst} and started system-gateway.service")
        print("   Check status: systemctl status system-gateway")
        print(f"   Secret: {secret_file}")
        return 0

    if platform == "darwin":
        dst = _launchd_plist_path()
        raw = src.read_text(encoding="utf-8")
        home = str(Path.home())
        raw = raw.replace("/Users/me", home)
        dst.write_text(raw, encoding="utf-8")
        _run_or_warn(["launchctl", "unload", str(dst)])
        _run_or_warn(["launchctl", "load", "-w", str(dst)])
        print(f"✅ Installed {dst} and loaded com.twin.system-gateway")
        print("   Check status: launchctl list | grep com.twin.system-gateway")
        print(f"   Secret: {secret_file}")
        return 0

    return 1  # pragma: no cover


def _cmd_uninstall(args: argparse.Namespace) -> int:
    """Stop and remove the native service."""

    if sys.platform.startswith("linux"):
        if not _is_root():
            print("❌ Linux uninstall requires root.", file=sys.stderr)
            return 1
        _run_or_warn(["systemctl", "stop", "system-gateway"])
        _run_or_warn(["systemctl", "disable", "system-gateway"])
        dst = _systemd_unit_path()
        if dst.exists():
            dst.unlink()
        _run_or_warn(["systemctl", "daemon-reload"])
        print("✅ Removed system-gateway.service")
        return 0

    if sys.platform == "darwin":
        dst = _launchd_plist_path()
        if dst.exists():
            _run_or_warn(["launchctl", "unload", str(dst)])
            dst.unlink()
        print("✅ Removed com.twin.system-gateway launch agent")
        return 0

    print("❌ Native uninstall is only supported on Linux and macOS.", file=sys.stderr)
    return 1


def _run_or_warn(cmd: list[str]) -> None:
    try:
        result = os.spawnvpe(os.P_WAIT, cmd[0], cmd, os.environ)
        if result != 0:
            logger.warning("Command %s exited with %d", cmd, result)
    except FileNotFoundError:
        logger.warning("Command not found: %s", cmd[0])


def _cmd_update(args: argparse.Namespace) -> int:
    """Request an in-place update from the running service."""

    url = (args.url or DEFAULT_URL).rstrip("/")
    secret = os.getenv("SYSTEM_GATEWAY_SHARED_SECRET")
    if not secret:
        secret_file = os.getenv("SYSTEM_GATEWAY_SHARED_SECRET_FILE")
        if secret_file:
            secret = _read_secret_file(Path(secret_file))
    if not secret:
        print("❌ SYSTEM_GATEWAY_SHARED_SECRET is required to request an update.", file=sys.stderr)
        return 1

    # Import here so the CLI can still print help without importing auth helpers.
    from twin.shared.system_gateway.auth import (
        headers_from_signed,
        mint_approval_token,
        sign_request,
    )

    actor = "owner-cli"
    approval_id = mint_approval_token(
        secret=secret,
        action="self.update",
        actor=actor,
    )
    payload = {
        "approval_id": approval_id,
        "from_version": args.from_version or SERVICE_VERSION,
    }
    if args.target_version:
        payload["to_version"] = args.target_version

    body_bytes = json.dumps(payload).encode("utf-8")
    signed = sign_request(
        secret=secret,
        method="POST",
        path="/self/update",
        actor=actor,
        body=body_bytes,
    )
    headers = {"Content-Type": "application/json"}
    headers.update(headers_from_signed(signed))

    req = urllib.request.Request(
        f"{url}/self/update",
        data=body_bytes,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            data = json.loads(body)
        except Exception:
            data = {"error": body}
        print(f"❌ Update request failed: HTTP {exc.code}: {data.get('error')}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover
        print(f"❌ Update request failed: {exc}", file=sys.stderr)
        return 1

    if data.get("ok"):
        print(f"✅ {data.get('message') or 'update requested'}")
        return 0
    print(f"⚠️  Update request rejected: {data.get('error')}", file=sys.stderr)
    return 1


def _cmd_run(args: argparse.Namespace) -> int:
    """Run the gateway service in the foreground."""

    config = GatewayConfig.from_env()
    web.run_app(create_app(config), host=config.host, port=config.port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="system-gateway",
        description="Native System Gateway service CLI.",
    )
    parser.add_argument(
        "--url",
        default=os.getenv("SYSTEM_GATEWAY_URL", DEFAULT_URL),
        help="Base URL of the running gateway (default: %(default)s).",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    subparsers.add_parser("status", help="Show gateway health.")
    subparsers.add_parser("doctor", help="Health + capabilities + config checks.")
    subparsers.add_parser("capabilities", help="Show gateway capabilities.")
    subparsers.add_parser("logs", help="Tail native service logs.")

    pair_parser = subparsers.add_parser("pair", help="Generate and store shared secret.")
    pair_parser.add_argument(
        "--secret-file",
        default=None,
        help="Path to write the secret (default: platform config dir).",
    )
    pair_parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate even if a secret already exists.",
    )

    subparsers.add_parser("install", help="Install native service (Linux/macOS).")
    subparsers.add_parser("uninstall", help="Remove native service (Linux/macOS).")

    update_parser = subparsers.add_parser("update", help="Request an in-place update.")
    update_parser.add_argument(
        "--target-version",
        default=None,
        help="Target version to update to.",
    )
    update_parser.add_argument(
        "--from-version",
        default=None,
        help="Current version (default: CLI version).",
    )

    run_parser = subparsers.add_parser("run", help="Run the service in the foreground.")
    run_parser.add_argument(
        "--host",
        default=None,
        help="Bind host (default: config/env).",
    )
    run_parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Bind port (default: config/env).",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    command = args.command or "run"
    if command == "run":
        return _cmd_run(args)

    handler = {
        "status": _cmd_status,
        "doctor": _cmd_doctor,
        "capabilities": _cmd_capabilities,
        "logs": _cmd_logs,
        "pair": _cmd_pair,
        "install": _cmd_install,
        "uninstall": _cmd_uninstall,
        "update": _cmd_update,
    }.get(command)
    if handler is None:
        parser.print_help()
        return 2
    return handler(args)
