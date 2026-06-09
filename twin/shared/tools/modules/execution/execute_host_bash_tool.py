"""
ExecuteHostBashTool - Chạy lệnh bash trên host machine.

Proxy Tool Pattern: tool này là BaseTool bình thường trong ToolRegistry,
nhưng execute() bên trong gọi HTTP ra host Bash Executor + kiểm tra ApprovalGate.

Không thay đổi ChatCoordinator, MCPClient, hay MCPServer.
"""

import logging
import re
from typing import Dict, Any, Optional

import aiohttp

from twin.shared.tools.registry.base import BaseTool, ToolExecutionError
from twin.shared.tools.approval_gate import ApprovalGate
from twin.shared.tools.exceptions import BashExecutorUnavailableError

logger = logging.getLogger(__name__)


class ExecuteHostBashTool(BaseTool):
    """
    Tool chạy lệnh bash trên host machine.

    Proxy pattern: tool trong container, thực thi trên host qua HTTP.
    Có ApprovalGate bảo vệ trước mỗi lần chạy.

    Attributes:
        approval_gate: Trạm Gác kiểm duyệt lệnh
        executor_url: URL của Bash Executor trên host
        timeout: Timeout mặc định cho HTTP request (giây)
        _session: aiohttp ClientSession (lazy)
    """

    def __init__(
        self,
        approval_gate: ApprovalGate,
        executor_url: str = "http://host.docker.internal:8374",
        timeout: int = 30,
    ):
        """
        Initialize tool.

        Args:
            approval_gate: ApprovalGate instance để kiểm duyệt
            executor_url: URL của host Bash Executor
            timeout: Timeout HTTP request (giây)
        """
        self.approval_gate = approval_gate
        self.executor_url = executor_url.rstrip("/")
        self.timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None

        logger.debug(f"ExecuteHostBashTool initialized: url={executor_url}, timeout={timeout}s")

    # ==========================================
    # BASE TOOL PROPERTIES
    # ==========================================

    @property
    def name(self) -> str:
        return "execute_host_bash"

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Lệnh cần chạy."
                },
                "timeout": {
                    "type": "integer",
                    "description": "Giây, tối đa 120."
                }
            },
            "required": ["command"]
        }

    # ==========================================
    # EXECUTION
    # ==========================================

    async def execute(self, command: str, timeout: int = 30) -> str:
        """
        Thực thi lệnh bash trên host.

        Args:
            command: Lệnh bash
            timeout: Timeout (giây), clamp 5-120

        Returns:
            str: Kết quả đã format
        """
        if not command or not command.strip():
            return "Lỗi: Vui lòng cung cấp lệnh bash cần chạy."

        # Clamp timeout
        timeout = max(5, min(120, timeout))

        # 1. Clean markdown wrapping
        command = self._clean_command(command.strip())
        logger.debug(f"Cleaned command: {command[:80]}")

        # 2. Trạm Gác - kiểm duyệt trước khi thực thi
        approved = await self.approval_gate.check_approval(
            tool_name=self.name,
            command=command,
        )

        if not approved:
            return "❌ Lệnh bị từ chối bởi Trạm Gác. Vui lòng thử lại hoặc kiểm tra quyền."

        # 3. Gọi host Bash Executor
        try:
            result = await self._call_executor(command, timeout)
            return self._format_result(command, result, timeout)
        except ToolExecutionError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error in execute_host_bash: {e}")
            raise ToolExecutionError(self.name, f"Lỗi không xác định: {e}", original_error=e)

    # ==========================================
    # HTTP CALL TO HOST EXECUTOR
    # ==========================================

    async def _call_executor(self, command: str, timeout: int) -> Dict[str, Any]:
        """
        Gọi HTTP POST tới host Bash Executor.

        Args:
            command: Lệnh đã clean
            timeout: Timeout cho cả HTTP + subprocess

        Returns:
            Dict: {"stdout": ..., "stderr": ..., "exit_code": ...}

        Raises:
            ToolExecutionError: Nếu không kết nối được hoặc timeout
        """
        session = await self._get_session()
        url = f"{self.executor_url}/execute"

        payload = {
            "command": command,
            "timeout": timeout,
        }
        headers = {
            "Content-Type": "application/json",
            "Origin": "march7-bot",
        }

        logger.debug(f"POST {url} | command={command[:60]} | timeout={timeout}")

        try:
            async with session.post(
                url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout + 5),  # HTTP timeout > command timeout
            ) as response:
                data = await response.json()

                if response.status == 403:
                    return {"error": "Forbidden: Origin not allowed"}
                elif response.status == 408:
                    return {"error": f"Lệnh bị timeout sau {timeout}s"}
                elif response.status >= 400:
                    error_msg = data.get("error", f"HTTP {response.status}")
                    return {"error": error_msg}

                return {
                    "stdout": data.get("stdout", ""),
                    "stderr": data.get("stderr", ""),
                    "exit_code": data.get("exit_code", -1),
                }

        except aiohttp.ClientConnectionError as e:
            logger.error(f"Không kết nối được Bash Executor: {e}")
            raise BashExecutorUnavailableError(
                executor_url=self.executor_url,
                message=f"Không kết nối được đến Bash Executor tại {self.executor_url}. Hãy khởi động service.",
            )
        except aiohttp.ClientError as e:
            logger.error(f"HTTP error khi gọi Bash Executor: {e}")
            return {"error": f"Lỗi giao tiếp với Bash Executor: {e}"}

    async def _get_session(self) -> aiohttp.ClientSession:
        """
        Get or create aiohttp session (lazy initialization).

        Pattern từ TavilyClient.

        Returns:
            aiohttp.ClientSession: HTTP client session
        """
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout + 10)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        """Close aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.debug("ExecuteHostBashTool session closed")

    # ==========================================
    # COMMAND CLEANING
    # ==========================================

    def _clean_command(self, command: str) -> str:
        """
        Loại bỏ markdown code block wrapping.

        LLM thường gửi lệnh trong ```bash ... ``` hoặc ```sh ... ```

        Args:
            command: Raw command từ LLM

        Returns:
            str: Cleaned command
        """
        # Remove leading/trailing whitespace
        command = command.strip()

        # Pattern: ```<lang>\n<command>\n```
        # Match ```bash, ```sh, ```shell, ``` (no lang)
        code_block_pattern = r'^```(?:bash|sh|shell|zsh|python|cmd|powershell)?\s*\n(.*?)\n```\s*$'
        match = re.match(code_block_pattern, command, re.DOTALL)
        if match:
            return match.group(1).strip()

        # Also handle inline code: `command`
        if command.startswith("`") and command.endswith("`") and not command.startswith("``"):
            return command[1:-1].strip()

        return command

    # ==========================================
    # RESULT FORMATTING
    # ==========================================

    def _format_result(self, command: str, result: Dict[str, Any], timeout: int) -> str:
        """
        Format kết quả từ host Bash Executor thành chuỗi hiển thị.

        Args:
            command: Lệnh đã chạy
            result: Dict từ executor {"stdout", "stderr", "exit_code"} hoặc {"error"}
            timeout: Timeout đã dùng

        Returns:
            str: Kết quả format
        """
        if "error" in result:
            return f"❌ **Lỗi:** {result['error']}"

        lines = []
        lines.append(f"🖥️ **Lệnh:** `{command[:80]}`")

        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        exit_code = result.get("exit_code", -1)

        if stdout:
            truncated_stdout = self._truncate_output(stdout, 4000)
            lines.append(f"📤 **stdout:**")
            lines.append(f"```\n{truncated_stdout}\n```")

        if stderr:
            truncated_stderr = self._truncate_output(stderr, 2000)
            lines.append(f"⚠️ **stderr:**")
            lines.append(f"```\n{truncated_stderr}\n```")

        if exit_code == 0:
            lines.append(f"✅ Exit code: 0 (thành công)")
        else:
            lines.append(f"⚠️ Exit code: {exit_code}")

        if not stdout and not stderr:
            lines.append("(không có output)")

        return "\n".join(lines)

    def _truncate_output(self, text: str, max_chars: int = 4000) -> str:
        """
        Cắt output nếu quá dài, giữ đầu và cuối.

        Args:
            text: Output text
            max_chars: Số ký tự tối đa

        Returns:
            str: Text đã cắt
        """
        if len(text) <= max_chars:
            return text

        half = max_chars // 2
        head = text[:half]
        tail = text[-half:]

        return f"{head}\n... [truncated: {len(text)} chars total] ...\n{tail}"

    def __repr__(self) -> str:
        return f"<ExecuteHostBashTool: url={self.executor_url}>"
