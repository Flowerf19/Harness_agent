"""
CodeBoxClient - Python code execution client for AI agents.

CodeBox provides a sandboxed Jupyter kernel environment for:
- Mathematical calculations
- Data analysis/manipulation
- Script testing
- Chart generation (matplotlib)

Architecture:
- Per-user sessions (stateful - variables persist across calls)
- Session TTL cleanup (30 minutes default)
- Direct HTTP client to local Docker CodeBox container

Local CodeBox Docker API:
- Endpoint: POST /exec
- Body: {"code": "...", "kernel": "ipython"}
- Response: XML-ish format <txt>output</txt><err>error</err>

Note: codeboxapi library is designed for cloud service (uses /codebox/{session_id}/exec)
      Local Docker uses simpler /exec endpoint, so we use httpx directly.
"""

import logging
import asyncio
import time
import re
from typing import Optional, Dict, Any
from dataclasses import dataclass, field

import httpx

from src.config.settings import Config

logger = logging.getLogger(__name__)


class CodeBoxError(Exception):
    """
    Exception raised when CodeBox execution fails.

    Attributes:
        message: Error message
        original_error: Original exception (if any)
    """

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        self.message = message
        self.original_error = original_error
        super().__init__(f"CodeBox Error: {message}")

    def __repr__(self) -> str:
        return f"CodeBoxError(message={self.message})"


@dataclass
class UserSession:
    """
    Per-user CodeBox session with TTL tracking.

    Local CodeBox Docker is stateless per request, but Jupyter kernel
    maintains state per container. We use session_id to identify user's
    kernel state within the container.

    Attributes:
        user_id: Discord user ID
        session_id: Unique session identifier (used as kernel identifier)
        http_client: httpx AsyncClient for this session
        created_at: Creation timestamp
        last_used_at: Last activity timestamp
    """

    user_id: str
    session_id: str
    http_client: httpx.AsyncClient
    created_at: float = field(default_factory=time.time)
    last_used_at: float = field(default_factory=time.time)

    def is_expired(self, ttl_seconds: int) -> bool:
        """Check if session has expired based on TTL."""
        return (time.time() - self.last_used_at) > ttl_seconds

    def touch(self):
        """Update last_used_at timestamp."""
        self.last_used_at = time.time()


class CodeBoxClient:
    """
    CodeBox API Client with per-user session management.

    Features:
    - Stateful sessions: Variables persist across calls per user
    - TTL cleanup: Expired sessions are automatically cleaned up
    - Timeout protection: Code execution limited to configured timeout

    Uses direct HTTP calls to local CodeBox Docker container.

    Example:
        client = CodeBoxClient()
        result = await client.run_code(user_id="123", code="x = 5 + 3\\nprint(x)")
        # Later, same user can access 'x':
        result = await client.run_code(user_id="123", code="print(x * 2)")
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
        timeout: Optional[int] = None,
        max_output_chars: Optional[int] = None,
        session_ttl: Optional[int] = None,
    ):
        """
        Initialize CodeBoxClient.

        Args:
            api_url: CodeBox API URL (default: from Config)
            timeout: Execution timeout in seconds (default: from Config)
            max_output_chars: Max output characters (default: from Config)
            session_ttl: Session TTL in seconds (default: from Config)
        """
        self.api_url = api_url or Config.CODEBOX_API_URL
        self.timeout = timeout or Config.CODEBOX_TIMEOUT
        self.max_output_chars = max_output_chars or Config.CODEBOX_MAX_OUTPUT_CHARS
        self.session_ttl = session_ttl or Config.CODEBOX_SESSION_TTL

        # Per-user sessions dict
        self._sessions: Dict[str, UserSession] = {}

        # Lock for session operations
        self._lock = asyncio.Lock()

        logger.info(
            f"CodeBoxClient initialized - url: {self.api_url}, "
            f"timeout: {self.timeout}s, ttl: {self.session_ttl}s"
        )

    async def _cleanup_expired_sessions(self):
        """Remove expired sessions."""
        expired_users = [
            user_id for user_id, session in self._sessions.items()
            if session.is_expired(self.session_ttl)
        ]

        for user_id in expired_users:
            try:
                await self._sessions[user_id].http_client.aclose()
                del self._sessions[user_id]
                logger.debug(f"Session expired and cleaned up for user: {user_id}")
            except Exception as e:
                logger.warning(f"Failed to cleanup session for {user_id}: {e}")
                del self._sessions[user_id]

        if expired_users:
            logger.info(f"Cleaned up {len(expired_users)} expired sessions")

    async def _get_or_create_session(self, user_id: str) -> UserSession:
        """
        Get existing session or create new one for user.

        Args:
            user_id: Discord user ID

        Returns:
            UserSession: Active session for the user
        """
        async with self._lock:
            # Cleanup expired sessions first
            await self._cleanup_expired_sessions()

            # Check if session exists
            if user_id in self._sessions:
                session = self._sessions[user_id]
                session.touch()
                return session

            # Create new session with dedicated HTTP client
            logger.info(f"Creating new CodeBox session for user: {user_id}")
            
            # Create session_id from user_id (used to identify kernel state)
            session_id = f"user_{user_id}"
            
            # Create httpx client with timeout
            client = httpx.AsyncClient(
                base_url=self.api_url,
                timeout=httpx.Timeout(self.timeout + 5),  # Extra buffer for HTTP
            )

            session = UserSession(
                user_id=user_id,
                session_id=session_id,
                http_client=client,
            )
            self._sessions[user_id] = session

            return session

    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """
        Parse CodeBox response XML-ish format.

        Response format:
        - <txt>output text</txt>
        - <err>error message</err>
        - <img>base64 image</img>

        Args:
            response_text: Raw response text from CodeBox

        Returns:
            Dict with 'output' and 'error' fields
        """
        output = ""
        error = False

        # Extract text output
        txt_match = re.search(r"<txt>(.*?)</txt>", response_text, re.DOTALL)
        if txt_match:
            output = txt_match.group(1)

        # Extract error
        err_match = re.search(r"<err>(.*?)</err>", response_text, re.DOTALL)
        if err_match:
            error_text = err_match.group(1)
            if error_text.strip():
                output = error_text
                error = True

        return {
            "output": output.strip(),
            "error": error,
        }

    async def run_code(self, user_id: str, code: str) -> Dict[str, Any]:
        """
        Execute Python code in user's sandboxed session.

        Args:
            user_id: Discord user ID
            code: Python code to execute

        Returns:
            Dict containing:
                - output: Execution output (stdout)
                - error: Error message if execution failed
                - success: True if execution succeeded

        Raises:
            CodeBoxError: If execution fails
        """
        if not code or not code.strip():
            raise CodeBoxError("Code cannot be empty")

        session = await self._get_or_create_session(user_id)

        try:
            logger.info(f"Executing code for user: {user_id} (length: {len(code)} chars)")

            # Execute code via HTTP POST
            response = await asyncio.wait_for(
                session.http_client.post(
                    "/exec",
                    json={"code": code, "kernel": "ipython"},
                ),
                timeout=self.timeout
            )

            # Check HTTP status
            if response.status_code != 200:
                raise CodeBoxError(f"HTTP error {response.status_code}: {response.text}")

            # Parse response
            parsed = self._parse_response(response.text)
            output = parsed["output"]
            has_error = parsed["error"]

            # Truncate if needed
            if len(output) > self.max_output_chars:
                half = self.max_output_chars // 2
                truncated_count = len(output) - self.max_output_chars
                output = (
                    f"{output[:half]}\n\n"
                    f"... [TRUNCATED {truncated_count} chars] ...\n\n"
                    f"{output[-half:]}"
                )
                logger.debug(f"Output truncated from {len(parsed['output'])} to {self.max_output_chars}")

            session.touch()

            return {
                "output": output,
                "error": has_error,
                "success": not has_error,
            }

        except asyncio.TimeoutError:
            logger.error(f"Code execution timeout for user: {user_id}")
            # Kill session on timeout
            await self._kill_session(user_id)
            raise CodeBoxError(f"Execution timeout after {self.timeout}s")

        except httpx.HTTPError as e:
            logger.error(f"HTTP error for user {user_id}: {e}")
            raise CodeBoxError(f"HTTP error: {e}", original_error=e)

        except Exception as e:
            logger.error(f"Code execution error for user {user_id}: {e}")
            raise CodeBoxError(f"Execution failed: {e}", original_error=e)

    async def _kill_session(self, user_id: str):
        """Kill and remove a user's session."""
        async with self._lock:
            if user_id in self._sessions:
                try:
                    await self._sessions[user_id].http_client.aclose()
                except Exception:
                    pass
                del self._sessions[user_id]
                logger.info(f"Session killed for user: {user_id}")

    async def close(self):
        """Close all sessions and cleanup."""
        async with self._lock:
            for user_id, session in self._sessions.items():
                try:
                    await session.http_client.aclose()
                except Exception as e:
                    logger.warning(f"Failed to close session for {user_id}: {e}")

            self._sessions.clear()
            logger.info("All CodeBox sessions closed")

    async def health_check(self) -> bool:
        """
        Check if CodeBox service is available.

        Returns:
            bool: True if service is healthy
        """
        try:
            async with httpx.AsyncClient(base_url=self.api_url, timeout=5) as client:
                response = await client.get("/")
                if response.status_code == 200:
                    data = response.json()
                    return data.get("status") == "ok"
                return False
        except Exception as e:
            logger.warning(f"CodeBox health check failed: {e}")
            return False

    def get_active_sessions_count(self) -> int:
        """Get number of active sessions."""
        return len(self._sessions)

    def __repr__(self) -> str:
        return f"<CodeBoxClient: url={self.api_url}, sessions={len(self._sessions)}>"