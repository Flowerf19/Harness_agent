"""Owner-only System Gateway administration tool for Evernight."""
from __future__ import annotations

import logging
from typing import Any

from twin.evernight.system_gateway import installer
from twin.evernight.system_gateway.monitor import GatewayMonitor
from twin.shared.system_gateway.auth import mint_approval_token
from twin.shared.tools.approval_context import get_current_approval_context
from twin.shared.tools.approval_gate import ApprovalGate
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
        approval_gate: ApprovalGate | None = None,
        base_url: str | None = None,
        shared_secret: str | None = None,
        timeout: int = 10,
        executor_url: str | None = None,
        bootstrap_repo_root: str | None = None,
        bootstrap_python: str | None = None,
        bootstrap_venv: str | None = None,
        bootstrap_timeout: int = 120,
    ):
        self.owner_user_id = str(owner_user_id)
        self._gateway_monitor = gateway_monitor
        self._host_gateway_client = host_gateway_client
        self._approval_gate = approval_gate
        self._base_url = base_url
        self._shared_secret = shared_secret
        self._timeout = timeout
        self._executor_url = executor_url
        self._bootstrap_repo_root = bootstrap_repo_root
        self._bootstrap_python = bootstrap_python
        self._bootstrap_venv = bootstrap_venv
        self._bootstrap_timeout = bootstrap_timeout

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
            },
            "required": ["command"],
        }

    async def execute(
        self,
        command: str,
        target_version: str | None = None,
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
            return self._install_hint()
        if cmd == "install":
            return await self._install()
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

    def _install_hint(self) -> str:
        return installer.build_bootstrap_hint().render_for_chat()

    async def _install(self) -> str:
        if not self._executor_url:
            return "❌ Bootstrap executor URL chưa được cấu hình."
        if not self._bootstrap_repo_root:
            return "❌ SYSTEM_GATEWAY_BOOTSTRAP_REPO_ROOT chưa được cấu hình."
        if not self._bootstrap_python:
            return "❌ SYSTEM_GATEWAY_BOOTSTRAP_PYTHON chưa được cấu hình."
        if self._approval_gate is None:
            return "❌ ApprovalGate chưa được cấu hình."

        bridge = installer.LegacyBashExecutorBootstrapBridge(
            executor_url=self._executor_url,
            repo_root=self._bootstrap_repo_root,
            python_executable=self._bootstrap_python,
            venv_path=self._bootstrap_venv or "/opt/system-gateway/venv",
            timeout=self._bootstrap_timeout,
        )
        command = bridge.build_install_command()
        approved = await self._approval_gate.check_approval(
            self.name,
            f"system-gateway bootstrap install:\n{command}",
        )
        if not approved:
            return "❌ Cài System Gateway bị từ chối bởi Trạm Gác."

        result = await bridge.install()
        lines = [
            (
                "✅ System Gateway bootstrap completed."
                if result.ok
                else f"⚠️ System Gateway bootstrap failed: {result.message}"
            )
        ]
        stdout = _redact_bootstrap_output(result.stdout)
        stderr = _redact_bootstrap_output(result.stderr)
        if stdout:
            lines.extend(["", "Output:", "```", _truncate(stdout, 3000), "```"])
        if stderr:
            lines.extend(["", "Stderr:", "```", _truncate(stderr, 2000), "```"])
        if self._gateway_monitor is not None:
            snapshot = await self._gateway_monitor.refresh_once()
            if hasattr(snapshot, "render_for_chat"):
                lines.extend(["", snapshot.render_for_chat()])
        return "\n".join(lines)

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


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return f"{text[:half]}\n... [truncated: {len(text)} chars total] ...\n{text[-half:]}"


def _redact_bootstrap_output(text: str) -> str:
    redacted_lines = []
    for line in (text or "").splitlines():
        if "SYSTEM_GATEWAY_SHARED_SECRET" in line:
            redacted_lines.append("[redacted system gateway secret line]")
        else:
            redacted_lines.append(line)
    return "\n".join(redacted_lines)
