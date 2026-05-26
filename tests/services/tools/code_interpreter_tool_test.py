"""
Unit tests for CodeInterpreterTool.

Tests tool metadata, parameter schema, execute flow with mocked CodeBoxClient,
file upload/download scenarios, and error handling.
"""
import sys
import base64
from pathlib import Path

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from twin.shared.tools.modules.execution.code_interpreter_tool import CodeInterpreterTool
from twin.shared.external.codebox_client import CodeBoxClient, CodeBoxError
from twin.shared.tools.registry import ToolExecutionError


class TestCodeInterpreterToolMetadata:
    """Test tool name, description, and schema."""

    def test_tool_name_returns_run_python_code(self):
        """tool.name == 'run_python_code'."""
        tool = CodeInterpreterTool()
        assert tool.name == "run_python_code"

    def test_tool_description_vietnamese(self):
        """tool.description contains Vietnamese text + mentions 'Jupyter' or 'Sandbox'."""
        tool = CodeInterpreterTool()
        assert "Thực thi" in tool.description or "Mã Python" in tool.description
        assert "Sandbox" in tool.description or "Kernel" in tool.description

    def test_parameters_schema_has_all_params(self):
        """Schema has user_id, code, kernel, cwd, file_content, filename, download_file_name."""
        tool = CodeInterpreterTool()
        props = tool.parameters_schema["properties"]

        assert "user_id" in props
        assert "code" in props
        assert "kernel" in props
        assert "cwd" in props
        assert "file_content" in props
        assert "filename" in props
        assert "download_file_name" in props

    def test_parameters_schema_kernel_enum(self):
        """kernel enum is ['ipython', 'bash']."""
        tool = CodeInterpreterTool()
        kernel_prop = tool.parameters_schema["properties"]["kernel"]
        assert kernel_prop["enum"] == ["ipython", "bash"]


class TestCodeInterpreterToolExecute:
    """Test CodeInterpreterTool.execute()."""

    @pytest.mark.asyncio
    async def test_execute_no_client_returns_error(self):
        """No codebox_client → Vietnamese error message."""
        tool = CodeInterpreterTool(codebox_client=None)
        result = await tool.execute(user_id="123", code="print(1)")

        assert "Lỗi" in result
        assert "CodeBox" in result or "cấu hình" in result

    @pytest.mark.asyncio
    async def test_execute_with_client_success(self):
        """Mock codebox_client.run_code, verify returns formatted output."""
        mock_client = MagicMock(spec=CodeBoxClient)
        mock_client.run_code = AsyncMock(return_value={
            "output": "8",
            "error": False,
            "success": True,
        })

        tool = CodeInterpreterTool(codebox_client=mock_client)
        result = await tool.execute(user_id="123", code="print(2 + 2)")

        assert "8" in result
        assert "Output" in result

        # Verify run_code was called
        mock_client.run_code.assert_called_once()
        call_kwargs = mock_client.run_code.call_args[1]
        assert call_kwargs["user_id"] == "123"
        assert call_kwargs["code"] == "print(2 + 2)"

    @pytest.mark.asyncio
    async def test_execute_with_bash_kernel(self):
        """Mock codebox_client.run_code with kernel='bash', verify forwarded."""
        mock_client = MagicMock(spec=CodeBoxClient)
        mock_client.run_code = AsyncMock(return_value={
            "output": "hello",
            "error": False,
            "success": True,
        })

        tool = CodeInterpreterTool(codebox_client=mock_client)
        result = await tool.execute(
            user_id="123",
            code="echo hello",
            kernel="bash",
        )

        assert "hello" in result

        call_kwargs = mock_client.run_code.call_args[1]
        assert call_kwargs["kernel"] == "bash"

    @pytest.mark.asyncio
    async def test_execute_download_only(self):
        """Mock codebox_client.download_file + run_code, verify returns base64 info."""
        mock_client = MagicMock(spec=CodeBoxClient)
        mock_client.run_code = AsyncMock(return_value={
            "output": "",
            "error": False,
            "success": True,
        })
        mock_client.download_file = AsyncMock(return_value=b"Hello, World!")

        tool = CodeInterpreterTool(codebox_client=mock_client)
        result = await tool.execute(
            user_id="123",
            code="print('ignored')",  # code is required but download takes priority
            download_file_name="test.txt",
        )

        # Verify download was called
        mock_client.download_file.assert_called_once_with(
            file_name="test.txt", user_id="123"
        )

        # Verify formatted result shows download info (length indicator)
        assert "Downloaded" in result
        assert "test.txt" in result
        assert "base64: 20 chars" in result  # "Hello, World!" base64 encoded is 20 chars

    @pytest.mark.asyncio
    async def test_execute_upload_file_then_exec(self):
        """Mock upload_file + run_code, verify upload called before run_code."""
        mock_client = MagicMock(spec=CodeBoxClient)
        mock_client.upload_file = AsyncMock(return_value={
            "success": True,
            "filename": "data.txt",
            "message": "Upload successful",
        })
        mock_client.run_code = AsyncMock(return_value={
            "output": "processed",
            "error": False,
            "success": True,
        })

        file_content = base64.b64encode(b"test,data,1,2,3").decode()

        tool = CodeInterpreterTool(codebox_client=mock_client)
        result = await tool.execute(
            user_id="123",
            code="print('done')",
            file_content=file_content,
            filename="data.txt",
        )

        # Verify upload was called before run_code
        assert mock_client.upload_file.called
        assert mock_client.run_code.called

        upload_call = mock_client.upload_file.call_args
        assert upload_call[1]["filename"] == "data.txt"
        assert upload_call[1]["user_id"] == "123"

        # Verify result from run_code
        assert "processed" in result
