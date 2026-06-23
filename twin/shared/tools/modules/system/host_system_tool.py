"""HostSystemTool - capability-based host interaction through System Gateway."""
from __future__ import annotations

import json
import logging
from typing import Any

from twin.shared.system_gateway import (
    GatewayActionRequest,
    GatewayShellRequest,
    HostGatewayClient,
    HostGatewayError,
    HostGatewayUnavailableError,
)
from twin.shared.tools.approval_gate import ApprovalGate
from twin.shared.tools.registry.base import BaseTool, ToolExecutionError

logger = logging.getLogger(__name__)


class HostSystemTool(BaseTool):
    """Capability-based host interaction via the native System Gateway."""

    def __init__(
        self,
        approval_gate: ApprovalGate,
        host_gateway_client: HostGatewayClient | None = None,
        host_gateway_timeout: int = 30,
    ):
        self.approval_gate = approval_gate
        self.host_gateway_client = host_gateway_client
        self.timeout = host_gateway_timeout

    @property
    def name(self) -> str:
        return "host_system"

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["capabilities", "action", "shell"],
                    "description": "Kiểu yêu cầu: capabilities, action, hoặc shell.",
                },
                "action": {
                    "type": "string",
                    "description": "Tên structured action, ví dụ system.status hoặc docker.list_containers.",
                },
                "arguments": {
                    "type": "object",
                    "description": "Tham số cho structured action.",
                },
                "command": {
                    "type": "string",
                    "description": "Lệnh raw shell khi mode=shell.",
                },
                "shell": {
                    "type": "string",
                    "description": "Shell mong muốn nếu gateway hỗ trợ, ví dụ bash/zsh/powershell.",
                },
                "cwd": {
                    "type": "string",
                    "description": "Thư mục làm việc cho raw shell.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout giây, mặc định 30, tối đa 120.",
                },
            },
            "required": ["mode"],
        }

    async def execute(
        self,
        mode: str,
        action: str | None = None,
        arguments: dict[str, Any] | None = None,
        command: str | None = None,
        shell: str | None = None,
        cwd: str | None = None,
        timeout: int | None = None,
    ) -> str:
        if not self.host_gateway_client:
            return (
                "❌ System Gateway chưa được cấu hình. "
                "Cần cài native `system-gateway` trên host và cấu hình URL trước."
            )

        timeout = max(5, min(120, timeout or self.timeout))
        mode = (mode or "").strip().lower()

        try:
            if mode == "capabilities":
                return await self._render_capabilities()
            if mode == "action":
                return await self._run_action(action, arguments or {}, timeout)
            if mode == "shell":
                return await self._run_shell(command, shell, cwd, timeout)
            return "Lỗi: mode phải là capabilities, action, hoặc shell."
        except HostGatewayUnavailableError as exc:
            return f"❌ System Gateway chưa sẵn sàng: {exc}"
        except HostGatewayError as exc:
            return f"❌ System Gateway lỗi: {exc}"
        except Exception as exc:
            logger.error("Unexpected host_system error: %s", exc)
            raise ToolExecutionError(self.name, f"Lỗi không xác định: {exc}", exc)

    async def _render_capabilities(self) -> str:
        capabilities = await self.host_gateway_client.capabilities()
        lines = [
            "🖥️ **System Gateway capabilities**",
            f"- Platform: {capabilities.platform}",
            f"- Raw shell: {'enabled' if capabilities.raw_shell else 'disabled'}",
        ]
        if capabilities.shells:
            lines.append(f"- Shells: {', '.join(capabilities.shells)}")
        if capabilities.features:
            lines.append(f"- Features: {', '.join(capabilities.features)}")
        if capabilities.structured_actions:
            lines.append(f"- Actions: {', '.join(capabilities.structured_actions)}")
        if capabilities.unsupported:
            lines.append(f"- Unsupported: {', '.join(capabilities.unsupported)}")
        if capabilities.notes:
            lines.append(f"- Notes: {'; '.join(capabilities.notes)}")
        return "\n".join(lines)

    async def _run_action(
        self,
        action: str | None,
        arguments: dict[str, Any],
        timeout: int,
    ) -> str:
        if not action or not action.strip():
            return "Lỗi: mode=action cần tham số action."

        action_name = action.strip()
        capabilities = await self.host_gateway_client.capabilities()
        if action_name not in capabilities.structured_actions:
            return (
                f"❌ System Gateway không hỗ trợ action `{action_name}` "
                f"trên platform {capabilities.platform}."
            )

        approval_text = (
            f"host action: {action_name} "
            f"{json.dumps(arguments, ensure_ascii=False)}"
        )
        approved = await self.approval_gate.check_approval(self.name, approval_text)
        if not approved:
            return "❌ Yêu cầu host_system bị từ chối bởi Trạm Gác."

        response = await self.host_gateway_client.run_action(
            GatewayActionRequest(
                action=action_name,
                arguments=arguments,
                timeout=timeout,
            )
        )
        return self._format_response(action_name, response.ok, response.output, response.error)

    async def _run_shell(
        self,
        command: str | None,
        shell: str | None,
        cwd: str | None,
        timeout: int,
    ) -> str:
        if not command or not command.strip():
            return "Lỗi: mode=shell cần tham số command."

        capabilities = await self.host_gateway_client.capabilities()
        if not capabilities.raw_shell:
            return "❌ Raw shell đang bị tắt trên System Gateway. Hãy dùng structured action nếu có."

        clean_command = command.strip()
        approval_text = f"host shell: {clean_command}"
        approved = await self.approval_gate.check_approval(self.name, approval_text)
        if not approved:
            return "❌ Lệnh host_system bị từ chối bởi Trạm Gác."

        response = await self.host_gateway_client.run_shell(
            GatewayShellRequest(
                command=clean_command,
                shell=shell,
                cwd=cwd,
                timeout=timeout,
            )
        )
        return self._format_response(clean_command, response.ok, response.output, response.error)

    def _format_response(
        self,
        label: str,
        ok: bool,
        output: str,
        error: str | None,
    ) -> str:
        lines = [f"🖥️ **Host:** `{label[:100]}`"]
        if output:
            lines.append("```")
            lines.append(self._truncate(output, 4000))
            lines.append("```")
        if error:
            lines.append(f"⚠️ {error}")
        lines.append("✅ Thành công" if ok else "⚠️ Không thành công")
        return "\n".join(lines)

    @staticmethod
    def _truncate(text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        half = max_chars // 2
        return f"{text[:half]}\n... [truncated: {len(text)} chars total] ...\n{text[-half:]}"
