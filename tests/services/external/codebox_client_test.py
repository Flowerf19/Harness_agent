"""
Unit tests for CodeBoxClient.

Tests initialization, configuration, code execution, file upload/download,
and error handling with mocked HTTP responses.
"""
import sys
from pathlib import Path

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from twin.shared.external.codebox_client import CodeBoxClient, CodeBoxError
from twin.shared.config.settings import Config


class TestCodeBoxClientInit:
    """Test CodeBoxClient initialization."""

    def test_init_default_config(self):
        """CodeBoxClient init uses Config defaults (api_url, timeout, max_output_chars, session_ttl)."""
        client = CodeBoxClient()

        assert client.api_url == Config.CODEBOX_API_URL
        assert client.timeout == Config.CODEBOX_TIMEOUT
        assert client.max_output_chars == Config.CODEBOX_MAX_OUTPUT_CHARS
        assert client.session_ttl == Config.CODEBOX_SESSION_TTL
        assert client._sessions == {}

    def test_init_overrides(self):
        """CodeBoxClient init with custom params."""
        client = CodeBoxClient(
            api_url="http://custom:9999",
            timeout=30,
            max_output_chars=1000,
            session_ttl=600,
        )

        assert client.api_url == "http://custom:9999"
        assert client.timeout == 30
        assert client.max_output_chars == 1000
        assert client.session_ttl == 600


class TestCodeBoxClientRunCode:
    """Test CodeBoxClient.run_code()."""

    def _make_mock_response(self, text="", error="", status_code=200):
        """Create a mock httpx response."""
        if error:
            body = f"<txt>{text}</txt><err>{error}</err>"
        else:
            body = f"<txt>{text}</txt><err></err>"
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.text = body
        return mock_resp

    @pytest.mark.asyncio
    async def test_run_code_basic_ipython(self):
        """Mock POST /exec 200 response, verify ExecBody has code + kernel='ipython'."""
        client = CodeBoxClient(api_url="http://test:8069")

        # Mock session creation
        mock_http_client = AsyncMock()
        mock_resp = self._make_mock_response(text="8")
        mock_http_client.post.return_value = mock_resp

        mock_session_obj = MagicMock()
        mock_session_obj.http_client = mock_http_client

        with patch.object(client, "_get_or_create_session", new_callable=AsyncMock, return_value=mock_session_obj) as mock_session:
            result = await client.run_code(user_id="123", code="print(2 + 2)")

            # Verify the POST was called with correct payload
            call_args = mock_http_client.post.call_args
            assert call_args[0][0] == "/exec"
            payload = call_args[1]["json"]
            assert payload["code"] == "print(2 + 2)"
            assert payload["kernel"] == "ipython"

            assert result["output"] == "8"
            assert result["error"] is False
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_run_code_with_kernel_bash(self):
        """Mock POST, verify payload has kernel='bash'."""
        client = CodeBoxClient(api_url="http://test:8069")

        mock_http_client = AsyncMock()
        mock_http_client.post.return_value = self._make_mock_response(text="hello")

        mock_session_obj = MagicMock()
        mock_session_obj.http_client = mock_http_client

        with patch.object(client, "_get_or_create_session", new_callable=AsyncMock, return_value=mock_session_obj):
            result = await client.run_code(user_id="123", code="echo hello", kernel="bash")

            call_args = mock_http_client.post.call_args
            payload = call_args[1]["json"]
            assert payload["kernel"] == "bash"

            assert result["output"] == "hello"
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_run_code_with_cwd(self):
        """Mock POST, verify payload has cwd='/workspace/subdir'."""
        client = CodeBoxClient(api_url="http://test:8069")

        mock_http_client = AsyncMock()
        mock_http_client.post.return_value = self._make_mock_response(text="/workspace/subdir")

        mock_session_obj = MagicMock()
        mock_session_obj.http_client = mock_http_client

        with patch.object(client, "_get_or_create_session", new_callable=AsyncMock, return_value=mock_session_obj):
            result = await client.run_code(
                user_id="123",
                code="import os; print(os.getcwd())",
                cwd="/workspace/subdir",
            )

            call_args = mock_http_client.post.call_args
            payload = call_args[1]["json"]
            assert payload["cwd"] == "/workspace/subdir"

            assert result["output"] == "/workspace/subdir"

    @pytest.mark.asyncio
    async def test_run_code_empty_code_raises(self):
        """Empty code → CodeBoxError."""
        client = CodeBoxClient(api_url="http://test:8069")

        with pytest.raises(CodeBoxError, match="empty"):
            await client.run_code(user_id="123", code="")

        with pytest.raises(CodeBoxError, match="empty"):
            await client.run_code(user_id="123", code="   ")

    @pytest.mark.asyncio
    async def test_run_code_http_error_raises(self):
        """Mock 500 response → CodeBoxError."""
        client = CodeBoxClient(api_url="http://test:8069")

        mock_http_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_http_client.post.return_value = mock_resp

        mock_session_obj = MagicMock()
        mock_session_obj.http_client = mock_http_client

        with patch.object(client, "_get_or_create_session", new_callable=AsyncMock, return_value=mock_session_obj):
            with pytest.raises(CodeBoxError, match="HTTP error 500"):
                await client.run_code(user_id="123", code="print('test')")


class TestCodeBoxClientUploadFile:
    """Test CodeBoxClient.upload_file()."""

    @pytest.mark.asyncio
    async def test_upload_file_bytes(self):
        """Mock POST /files/upload 200, verify multipart request sent."""
        client = CodeBoxClient(api_url="http://test:8069")

        mock_http_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "success": True,
            "filename": "test.txt",
            "message": "Upload successful",
        }
        mock_http_client.post.return_value = mock_resp

        mock_session_obj = MagicMock()
        mock_session_obj.http_client = mock_http_client

        with patch.object(client, "_get_or_create_session", new_callable=AsyncMock, return_value=mock_session_obj):
            result = await client.upload_file(
                file_content=b"Hello, World!",
                filename="test.txt",
                user_id="123",
            )

            # Verify POST was called
            assert mock_http_client.post.called
            call_args = mock_http_client.post.call_args
            assert call_args[0][0] == "/files/upload"

            # Verify result
            assert result["success"] is True
            assert result["filename"] == "test.txt"

    @pytest.mark.asyncio
    async def test_upload_file_invalid_filename_dotdot(self):
        """filename with '..' → CodeBoxError."""
        client = CodeBoxClient(api_url="http://test:8069")

        with pytest.raises(CodeBoxError, match="Invalid filename"):
            await client.upload_file(
                file_content=b"test",
                filename="../etc/passwd",
                user_id="123",
            )

    @pytest.mark.asyncio
    async def test_upload_file_invalid_filename_absolute(self):
        """filename='/etc/passwd' → CodeBoxError."""
        client = CodeBoxClient(api_url="http://test:8069")

        with pytest.raises(CodeBoxError, match="Invalid filename"):
            await client.upload_file(
                file_content=b"test",
                filename="/etc/passwd",
                user_id="123",
            )


class TestCodeBoxClientDownloadFile:
    """Test CodeBoxClient.download_file()."""

    @pytest.mark.asyncio
    async def test_download_file_success(self):
        """Mock GET /files/download/test.txt 200, returns bytes."""
        client = CodeBoxClient(api_url="http://test:8069")

        mock_http_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"Hello, World!"
        mock_http_client.get.return_value = mock_resp

        mock_session_obj = MagicMock()
        mock_session_obj.http_client = mock_http_client

        with patch.object(client, "_get_or_create_session", new_callable=AsyncMock, return_value=mock_session_obj):
            result = await client.download_file(file_name="test.txt", user_id="123")

            # Verify GET was called with correct path
            call_args = mock_http_client.get.call_args
            assert call_args[0][0] == "/files/download/test.txt"

            assert result == b"Hello, World!"

    @pytest.mark.asyncio
    async def test_download_file_invalid_name(self):
        """filename with special chars → CodeBoxError."""
        client = CodeBoxClient(api_url="http://test:8069")

        with pytest.raises(CodeBoxError, match="Invalid file name"):
            await client.download_file(file_name="test file.txt", user_id="123")

        with pytest.raises(CodeBoxError, match="Invalid file name"):
            await client.download_file(file_name="test/file.txt", user_id="123")

        with pytest.raises(CodeBoxError, match="Invalid file name"):
            await client.download_file(file_name="../test.txt", user_id="123")
