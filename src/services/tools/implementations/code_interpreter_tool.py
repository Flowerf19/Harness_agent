"""
CodeInterpreterTool - Python code execution in sandboxed environment.

Tool for executing Python code in a Jupyter kernel sandbox via CodeBox API.
Provides:
- Mathematical calculations (LLM can't reliably do mental math)
- Data manipulation/analysis
- Script testing
- Chart generation (matplotlib)

Architecture:
- Per-user sessions (stateful - variables persist across calls)
- TTL cleanup (30 minutes default)
- Timeout protection (60 seconds default)

Design Philosophy:
- Clear trigger boundaries defined in TOOL.md
- NOT used for: hardware info, web search, simple NLP tasks
"""

import logging
from typing import Dict, Any, Optional

from src.services.tools.base_tool import BaseTool, ToolExecutionError
from src.services.external.codebox_client import CodeBoxClient, CodeBoxError

logger = logging.getLogger(__name__)


class CodeInterpreterTool(BaseTool):
    """
    Python Code Execution Tool using CodeBox sandbox.

    Executes Python code in an isolated Jupyter kernel environment.
    Variables and functions persist across calls (stateful per-user sessions).

    Attributes:
        codebox_client: CodeBoxClient for sandboxed code execution

    Example:
        tool = CodeInterpreterTool(codebox_client)
        result = await tool.execute(user_id="123", code="print(5 + 3)")
    """

    def __init__(self, codebox_client: Optional[CodeBoxClient] = None):
        """
        Initialize CodeInterpreterTool.

        Args:
            codebox_client: CodeBoxClient for code execution (can be None for graceful degradation)
        """
        self.codebox_client = codebox_client
        logger.info(
            f"CodeInterpreterTool initialized - client: {codebox_client is not None}"
        )

    # ==========================================
    # BASE TOOL PROPERTIES
    # ==========================================

    @property
    def name(self) -> str:
        return "run_python_code"

    @property
    def description(self) -> str:
        return (
            "Thực thi mã Python trong môi trường Sandbox (Jupyter Kernel). "
            "Dùng cho: Tính toán, phân tích data, test script. "
            "Chi tiết cách dùng và khi nào KHÔNG dùng xem TOOL.md."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": (
                        "Discord user ID (số) của user đang chat. "
                        "VD: '726302130318868500'. "
                        "Biến khai báo sẽ được lưu riêng cho từng user."
                    )
                },
                "code": {
                    "type": "string",
                    "description": (
                        "Mã Python cần thực thi. "
                        "KHÔNG bao gồm markdown ticks (```python). "
                        "VD: 'x = [1,2,3]\\nprint(sum(x))'"
                    )
                },
            },
            "required": ["user_id", "code"]
        }

    # ==========================================
    # EXECUTION
    # ==========================================

    async def execute(
        self,
        user_id: str,
        code: str,
    ) -> str:
        """
        Execute Python code in sandboxed environment.

        Args:
            user_id: Discord user ID (numeric) - determines session
            code: Python code to execute (no markdown ticks)

        Returns:
            str: Execution output or error message
        """
        # Validate user_id
        if not user_id:
            return "Lỗi: Thiếu user_id."

        if not user_id.isdigit():
            logger.warning(f"Invalid user_id: {user_id} - không phải số")
            return f"Lỗi: user_id '{user_id}' không hợp lệ. user_id phải là số ID của Discord user."

        # Validate code
        if not code or not code.strip():
            return "Lỗi: Code không được để trống."

        # Clean code - remove markdown ticks if present
        code = self._clean_code(code)

        # Check if client is available
        if not self.codebox_client:
            return "Lỗi: Code Sandbox chưa được cấu hình. Vui lòng bật CodeBox service."

        # Execute code
        try:
            logger.info(
                f"🐍 Code execution: user={user_id}, "
                f"length={len(code)} chars"
            )

            result = await self.codebox_client.run_code(
                user_id=user_id,
                code=code
            )

            # Format result
            return self._format_result(result)

        except CodeBoxError as e:
            logger.error(f"CodeBox error: {e.message}")
            return self._format_error(e)

        except Exception as e:
            logger.error(f"Unexpected error in CodeInterpreterTool: {e}")
            raise ToolExecutionError(
                self.name,
                f"Lỗi không xác định: {e}",
                original_error=e
            )

    # ==========================================
    # HELPER METHODS
    # ==========================================

    def _clean_code(self, code: str) -> str:
        """
        Clean code input - remove markdown ticks if present.

        Args:
            code: Raw code string (may have markdown formatting)

        Returns:
            str: Clean Python code
        """
        code = code.strip()

        # Remove markdown code blocks
        if code.startswith("```python"):
            code = code[9:]
        elif code.startswith("```"):
            code = code[3:]

        if code.endswith("```"):
            code = code[:-3]

        return code.strip()

    def _format_result(self, result: Dict[str, Any]) -> str:
        """
        Format execution result for user.

        Args:
            result: Dict with 'output', 'error', 'success'

        Returns:
            str: Formatted result string
        """
        output = result.get("output", "")
        has_error = result.get("error", False)

        if has_error:
            return (
                f"❌ **Code Error:**\n"
                f"{output}\n\n"
                f"💡 Hãy phân tích lỗi và sửa lại code. "
                f"Kiểm tra syntax, imports, và variable names."
            )

        if not output:
            return (
                "✅ Code executed successfully (no output).\n\n"
                "💡 Nếu cần xem biến, hãy dùng `print()` để hiển thị."
            )

        return f"✅ **Output:**\n{output}"

    def _format_error(self, error: CodeBoxError) -> str:
        """
        Format CodeBox error for user.

        Args:
            error: CodeBoxError instance

        Returns:
            str: User-friendly error message
        """
        message = error.message.lower()

        if "timeout" in message:
            return (
                "❌ **Execution Timeout:**\n"
                f"Code chạy quá lâu (>60s). Có thể có infinite loop hoặc calculation quá phức tạp.\n\n"
                "💡 Hãy tối ưu code hoặc chia nhỏ thành các bước."
            )
        elif "connection" in message or "network" in message:
            return (
                "❌ **Connection Error:**\n"
                "Không thể kết nối đến CodeBox service.\n\n"
                "💡 Vui lòng thử lại sau hoặc thông báo admin."
            )
        else:
            return f"❌ **Error:** {error.message}"

    def __repr__(self) -> str:
        return f"<CodeInterpreterTool: client={self.codebox_client is not None}>"