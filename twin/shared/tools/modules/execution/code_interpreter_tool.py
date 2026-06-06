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
- Clear trigger boundaries defined in the lazy tool guide.
- NOT used for: hardware info, web search, simple NLP tasks
"""

import logging
from typing import Dict, Any, Optional

from twin.shared.tools.registry.base import BaseTool, ToolExecutionError
from twin.shared.external.codebox_client import CodeBoxClient, CodeBoxError

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
        logger.debug(
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
        return "Thực thi code trong Sandbox."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "Discord user ID."
                },
                "code": {
                    "type": "string",
                    "description": "Code, không bọc markdown fence."
                },
                "kernel": {
                    "type": "string",
                    "enum": ["ipython", "bash"],
                    "description": "ipython hoặc bash."
                },
                "cwd": {
                    "type": "string",
                    "description": "Thư mục làm việc."
                },
                "file_content": {
                    "type": "string",
                    "description": "Nội dung upload dạng base64."
                },
                "filename": {
                    "type": "string",
                    "description": "Tên file upload."
                },
                "download_file_name": {
                    "type": "string",
                    "description": "Tên file cần tải về."
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
        kernel: Optional[str] = None,
        cwd: Optional[str] = None,
        file_content: Optional[str] = None,
        filename: Optional[str] = None,
        download_file_name: Optional[str] = None,
    ) -> str:
        """
        Execute Python code in sandboxed environment.

        Args:
            user_id: Discord user ID (numeric) - determines session
            code: Python code to execute (no markdown ticks)
            kernel: Kernel type - "ipython" (default) or "bash"
            cwd: Working directory
            file_content: Base64 encoded file content to upload
            filename: Filename for upload
            download_file_name: Filename to download

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

        # Validate kernel - default to ipython
        if kernel is None:
            kernel = "ipython"
        elif kernel not in ("ipython", "bash"):
            logger.warning(f"Invalid kernel '{kernel}', defaulting to ipython")
            kernel = "ipython"

        # Execute code
        try:
            logger.debug(
                f"🐍 Code execution: user={user_id}, kernel={kernel}, "
                f"cwd={cwd}, length={len(code)} chars"
            )

            # Handle file upload if provided
            upload_result = None
            if file_content and filename:
                import base64
                try:
                    file_bytes = base64.b64decode(file_content)
                    upload_result = await self.codebox_client.upload_file(
                        file_content=file_bytes,
                        filename=filename,
                        user_id=user_id,
                    )
                    logger.debug(f"File uploaded: {filename}")
                except Exception as e:
                    logger.error(f"Upload error: {e}")
                    return f"❌ **Upload Error:** {e}"

            # Execute code
            result = await self.codebox_client.run_code(
                user_id=user_id,
                code=code,
                kernel=kernel,
                cwd=cwd,
            )

            # Handle file download if requested
            download_result = None
            if download_file_name:
                try:
                    file_bytes = await self.codebox_client.download_file(
                        file_name=download_file_name,
                        user_id=user_id,
                    )
                    import base64
                    download_result = base64.b64encode(file_bytes).decode("utf-8")
                    logger.debug(f"File downloaded: {download_file_name} ({len(file_bytes)} bytes)")
                except Exception as e:
                    logger.error(f"Download error: {e}")
                    # Don't fail completely - still return code result
                    download_result = f"ERROR: {e}"

            # Format result
            output = self._format_result(result)

            # Add upload/download info if applicable
            if upload_result:
                output += f"\n\n📁 **Uploaded:** {filename}"
            if download_result and not download_result.startswith("ERROR"):
                output += f"\n\n📁 **Downloaded:** {download_file_name} (base64: {len(download_result)} chars)"

            return output

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
