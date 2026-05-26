"""
Integration tests for CodeBoxClient against real Docker container.

These tests require a running CodeBox service at CODEBOX_API_URL.
All tests are skipped if the service is unreachable.

Run with: pytest tests/services/external/codebox_integration_test.py -v
"""
import sys
import os
import uuid
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from twin.shared.external.codebox_client import CodeBoxClient, CodeBoxError
from twin.shared.config.settings import Config


def _is_codebox_reachable() -> bool:
    """Check if CodeBox service is reachable via health check."""
    import asyncio
    import httpx

    api_url = Config.CODEBOX_API_URL

    async def _check():
        try:
            client = CodeBoxClient(api_url=api_url)
            healthy = await client.health_check()
            await client.close()
            return healthy
        except Exception:
            return False

    return asyncio.run(_check())


# Module-level skip: integration tests are opt-in to avoid network/service
# probes during normal unit test collection.
pytestmark = pytest.mark.skipif(
    os.getenv("RUN_CODEBOX_INTEGRATION") != "1" or not _is_codebox_reachable(),
    reason="Set RUN_CODEBOX_INTEGRATION=1 with reachable CODEBOX_API_URL to run",
)


class TestCodeBoxIntegration:
    """Integration tests against real CodeBox Docker container."""

    @pytest.mark.asyncio
    async def test_real_ipython_exec(self):
        """print(2 + 2) → output contains '4'."""
        user_id = f"test_ipython_{uuid.uuid4().hex[:8]}"
        client = CodeBoxClient()

        try:
            result = await client.run_code(
                user_id=user_id,
                code="print(2 + 2)",
                kernel="ipython",
            )

            assert result["success"] is True
            assert "4" in result["output"]
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_real_bash_exec(self):
        """kernel='bash', echo hello → output contains 'hello'."""
        user_id = f"test_bash_{uuid.uuid4().hex[:8]}"
        client = CodeBoxClient()

        try:
            result = await client.run_code(
                user_id=user_id,
                code="echo hello",
                kernel="bash",
            )

            assert result["success"] is True
            assert "hello" in result["output"]
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_real_cwd_override(self):
        """cwd='/workspace', import os; print(os.getcwd()) → output '/workspace'."""
        user_id = f"test_cwd_{uuid.uuid4().hex[:8]}"
        client = CodeBoxClient()

        try:
            result = await client.run_code(
                user_id=user_id,
                code="import os; print(os.getcwd())",
                kernel="ipython",
                cwd="/workspace",
            )

            assert result["success"] is True
            assert "/workspace" in result["output"]
        except CodeBoxError as e:
            # Some CodeBox versions don't support cwd parameter
            pytest.skip(f"CodeBox doesn't support cwd parameter: {e.message}")
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_real_session_persistence(self):
        """Call 1: x = 42, Call 2: print(x) → output '42' (same user_id)."""
        user_id = f"test_session_{uuid.uuid4().hex[:8]}"
        client = CodeBoxClient()

        try:
            # Call 1: Set variable
            result1 = await client.run_code(
                user_id=user_id,
                code="x = 42",
                kernel="ipython",
            )
            assert result1["success"] is True

            # Call 2: Access same variable
            result2 = await client.run_code(
                user_id=user_id,
                code="print(x)",
                kernel="ipython",
            )

            assert result2["success"] is True
            assert "42" in result2["output"]
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_real_upload_download_roundtrip(self):
        """Upload text content as 'test.txt' → exec code reads it → download 'test.txt' → content matches."""
        user_id = f"test_upload_{uuid.uuid4().hex[:8]}"
        client = CodeBoxClient()
        original_content = b"Hello from integration test!\nLine 2\nLine 3\n"
        filename = "test_roundtrip.txt"

        try:
            # Upload
            upload_result = await client.upload_file(
                file_content=original_content,
                filename=filename,
                user_id=user_id,
            )
            assert upload_result["success"] is True

            # Execute code that reads the file (try both /workspace/ and current dir)
            read_code = f"""
import os
# Try to find the file
paths_to_try = ['{filename}', f'/workspace/{filename}']
for p in paths_to_try:
    if os.path.exists(p):
        with open(p, 'r') as f:
            print(f.read())
        break
else:
    print(f"File not found, listing: {{os.listdir('.')}}")
"""
            exec_result = await client.run_code(
                user_id=user_id,
                code=read_code,
                kernel="ipython",
            )
            # Check if file was read successfully
            assert "Hello from integration test!" in exec_result["output"], (
                f"File content not found in output: {exec_result['output']}"
            )

            # Download
            downloaded = await client.download_file(
                file_name=filename,
                user_id=user_id,
            )
            assert downloaded == original_content
        except CodeBoxError as e:
            pytest.skip(f"CodeBox upload/download not fully supported: {e.message}")
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_real_stateful_variables(self):
        """Call 1: data = [1,2,3,4,5], Call 2: print(sum(data)) → output '15'."""
        user_id = f"test_stateful_{uuid.uuid4().hex[:8]}"
        client = CodeBoxClient()

        try:
            # Call 1: Define data
            result1 = await client.run_code(
                user_id=user_id,
                code="data = [1, 2, 3, 4, 5]",
                kernel="ipython",
            )
            assert result1["success"] is True

            # Call 2: Use data
            result2 = await client.run_code(
                user_id=user_id,
                code="print(sum(data))",
                kernel="ipython",
            )

            assert result2["success"] is True
            assert "15" in result2["output"]
        finally:
            await client.close()
