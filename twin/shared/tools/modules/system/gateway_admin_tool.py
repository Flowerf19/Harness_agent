"""Owner-only System Gateway administration tool for Evernight."""
from __future__ import annotations

import logging
from typing import Any

from twin.evernight.host_gateway import installer
from twin.evernight.host_gateway.monitor import GatewayMonitor
from twin.shared.system_gateway.auth import mint_approval_token
from twin.shared.tools.approval_context import get_current_approval_context
from twin.shared.tools.registry.base import BaseTool

logger = logging.getLogger(__name__)


class GatewayAdminTool(BaseTool):
    """Owner-only System Gateway administration.

    This tool is visible only to Evernight. Every command verifies that the
    caller's user_id matches the configured owner before doing anything.
    """

    def __init__(
        self,
        owner_user_id: str,
        gateway_monitor: GatewayMonitor | None = None,
        host_gateway_client=None,
        base_url: str | None = None,
        shared_secret: str | None = None,
        timeout: int = 10,
    ):
        self.owner_user_id = str(owner_user_id)
        self._gateway_monitor = gateway_monitor
        self._host_gateway_client = host_gateway_client
        self._base_url = base_url
        self._shared_secret = shared_secret
        self._timeout = timeout

    @property
    def name(self) -> str:
        return "gateway_admin"

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "enum": ["status", "doctor", "install_hint", "install", "update"],
                    "description": "Lệnh quản trị gateway.",
                },
                "target_version": {
                    "type": "string",
                    "description": "Phiên bản mục tiêu khi command=update.",
                },
                "install_path": {
                    "type": "string",
                    "description": (
                        "Thư mục cài March7 trên host, hoặc path tới "
                        "scripts/bootstrap_system_gateway.py, khi command là "
                        "install/install_hint."
                    ),
                },
            },
            "required": ["command"],
        }

    async def execute(
        self,
        command: str,
        target_version: str | None = None,
        install_path: str | None = None,
        repo_root: str | None = None,
    ) -> str:
        if not self._is_owner():
            return "❌ Lệnh này chỉ dành cho owner."

        cmd = (command or "").strip().lower()
        if cmd == "status":
            if self._gateway_monitor is None:
                return "❌ GatewayMonitor chưa được cấu hình."
            return self._gateway_monitor.status_for_chat()
        if cmd == "doctor":
            return await self._doctor()
        if cmd == "install_hint":
            return self._install_hint(install_path=install_path or repo_root)
        if cmd == "install":
            return await self._install(install_path=install_path or repo_root)
        if cmd == "update":
            return await self._update(target_version)
        return (
            f"❌ Lệnh `{command}` không hợp lệ. "
            "Các lệnh hỗ trợ: status, doctor, install_hint, install, update."
        )

    def _is_owner(self) -> bool:
        context = get_current_approval_context()
        if context is None:
            logger.warning("gateway_admin: no approval context; rejecting as non-owner")
            return False
        caller = str(context.user_id or "").strip()
        owner = self.owner_user_id.strip()
        if not caller or not owner:
            return False
        return caller == owner

    async def _doctor(self) -> str:
        if self._gateway_monitor is None:
            return "❌ GatewayMonitor chưa được cấu hình."
        snapshot = await self._gateway_monitor.refresh_once()
        # refresh_once() may return None in tests/fakes; fall back to cached snapshot.
        if snapshot is None:
            snapshot = self._gateway_monitor.snapshot
        # Real snapshots have render_for_chat(); fakes may not — fall back to monitor.
        if hasattr(snapshot, "render_for_chat"):
            rendered = snapshot.render_for_chat()
        else:
            rendered = self._gateway_monitor.status_for_chat()
        lines = [rendered]
        status = getattr(snapshot, "status", None)
        status_value = getattr(status, "value", status)
        if status_value == "missing":
            lines.append("")
            lines.append(self._install_hint())
        return "\n".join(lines)

    def _install_hint(self, *, install_path: str | None = None) -> str:
        try:
            return installer.build_bootstrap_hint(install_path=install_path).render_for_chat()
        except ValueError as exc:
            return f"❌ install_path không hợp lệ: {exc}"

    async def _install(self, *, install_path: str | None = None) -> str:
        return "\n".join(
            [
                "Chạy trên host, không chạy trong container:",
                self._install_hint(install_path=install_path),
            ]
        )

    async def _update(self, target_version: str | None) -> str:
        if self._gateway_monitor is None:
            return "❌ GatewayMonitor chưa được cấu hình."

        current_version = self._gateway_monitor.snapshot.version
        if current_version is None:
            return "❌ Gateway chưa cài đặt hoặc không phản hồi — không thể update."

        base_url = self._base_url
        if base_url is None and self._host_gateway_client is not None:
            base_url = getattr(self._host_gateway_client, "base_url", None)
        if base_url is None and self._gateway_monitor is not None:
            base_url = getattr(self._gateway_monitor, "base_url", None)
        if base_url is None and self._gateway_monitor is not None:
            client = getattr(self._gateway_monitor, "_client", None)
            if client is not None:
                base_url = getattr(client, "base_url", None)
        if base_url is None:
            return "❌ Gateway base URL chưa được cấu hình."

        approval_id = None
        secret = self._shared_secret
        if secret is None and self._host_gateway_client is not None:
            secret = getattr(self._host_gateway_client, "shared_secret", None)
        if not secret:
            return "❌ Gateway shared secret chưa được cấu hình."
        actor = "evernight"
        if self._host_gateway_client is not None:
            actor = getattr(self._host_gateway_client, "actor", actor)
        if secret:
            approval_id = mint_approval_token(
                secret=secret,
                action="self.update",
                actor=actor,
            )

        coordinator = installer.InstallerCoordinator(
            base_url=base_url,
            timeout=self._timeout,
            shared_secret=secret,
            actor=actor,
        )

        ok, message = await coordinator.request_update(
            current_version=current_version,
            approval_id=approval_id,
            target_version=target_version,
        )
        if ok:
            return f"✅ Update request accepted: {message}"
        return f"⚠️ Update request failed: {message}"
