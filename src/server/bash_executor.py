"""
Bash Executor - HTTP endpoint chạy lệnh bash trên host.

ĐÂY KHÔNG PHẢI MCP SERVER. Đây là HTTP endpoint tối giản,
chỉ nhận POST request và chạy bash qua asyncio.subprocess.

Chạy standalone: python -m src.server.bash_executor

Security:
- Origin validation (chỉ bot container được gọi)
- Non-root user (chạy dưới user khởi động service)
- Timeout cho mọi lệnh
- Output truncation
"""

import asyncio
import logging
import time
import signal
import sys

from aiohttp import web

from src.server.config import BashExecutorConfig

logger = logging.getLogger(__name__)

# Track server start time for uptime
_start_time = time.time()


async def handle_health(request: web.Request) -> web.Response:
    """GET /health - Health check endpoint."""
    uptime = int(time.time() - _start_time)
    return web.json_response({
        "status": "ok",
        "uptime": uptime,
    })


def _validate_origin(request: web.Request) -> bool:
    """
    Validate Origin header against allowed origins.

    Chỉ cho phép request từ bot container (Origin: march7-bot).

    Args:
        request: aiohttp Request

    Returns:
        bool: True nếu origin hợp lệ
    """
    origin = request.headers.get("Origin", "")

    if not origin:
        logger.warning("Rejected: missing Origin header")
        return False

    for allowed in BashExecutorConfig.ALLOWED_ORIGINS:
        if origin.strip() == allowed.strip():
            return True

    logger.warning(f"Rejected: Origin '{origin}' not in allowed list")
    return False


async def handle_execute(request: web.Request) -> web.Response:
    """
    POST /execute - Chạy lệnh bash.

    Body: {"command": "...", "timeout": 30}
    Response: {"stdout": "...", "stderr": "...", "exit_code": 0}

    Security: validates Origin header trước khi chạy.
    """
    # Validate Origin
    if not _validate_origin(request):
        return web.json_response(
            {"error": "Forbidden: Origin not allowed"},
            status=403,
        )

    # Parse request body
    try:
        data = await request.json()
    except Exception:
        return web.json_response(
            {"error": "Invalid JSON body"},
            status=400,
        )

    command = data.get("command", "")
    timeout = data.get("timeout", BashExecutorConfig.DEFAULT_TIMEOUT)

    # Validate command
    if not command or not command.strip():
        return web.json_response(
            {"error": "Missing 'command' field"},
            status=400,
        )

    # Clamp timeout
    timeout = max(1, min(BashExecutorConfig.MAX_TIMEOUT, int(timeout)))

    logger.info(f"Executing: {command[:80]} (timeout={timeout}s)")

    # Execute command
    try:
        proc = await asyncio.create_subprocess_shell(
            command.strip(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            logger.warning(f"Command timed out after {timeout}s: {command[:60]}")
            return web.json_response(
                {"error": f"Command timed out after {timeout}s"},
                status=408,
            )

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        exit_code = proc.returncode

        # Truncate output
        max_chars = BashExecutorConfig.MAX_OUTPUT_CHARS
        stdout = _truncate(stdout, max_chars)
        stderr = _truncate(stderr, max_chars)

        logger.debug(
            f"Command completed: exit={exit_code}, "
            f"stdout={len(stdout)} chars, stderr={len(stderr)} chars"
        )

        return web.json_response({
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
        })

    except Exception as e:
        logger.error(f"Command execution error: {e}")
        return web.json_response(
            {"error": f"Execution failed: {e}"},
            status=500,
        )


def _truncate(text: str, max_chars: int) -> str:
    """Cắt text nếu quá dài, giữ đầu và cuối."""
    if len(text) <= max_chars:
        return text

    half = max_chars // 2 - 20
    head = text[:half]
    tail = text[-half:]
    return f"{head}\n... [truncated: {len(text)} chars total] ...\n{tail}"


def create_app() -> web.Application:
    """Create and configure aiohttp application."""
    app = web.Application()

    app.router.add_get("/health", handle_health)
    app.router.add_post("/execute", handle_execute)

    return app


def main():
    """Entry point: python -m src.server.bash_executor"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = BashExecutorConfig

    logger.info(f"Starting Bash Executor on {config.HOST}:{config.PORT}")
    logger.info(f"Allowed origins: {config.ALLOWED_ORIGINS}")
    logger.info(f"Max output: {config.MAX_OUTPUT_CHARS} chars")
    logger.info(f"Max timeout: {config.MAX_TIMEOUT}s")
    logger.info(f"Running as user: (non-root)")

    app = create_app()

    # Graceful shutdown
    def shutdown_handler(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    web.run_app(
        app,
        host=config.HOST,
        port=config.PORT,
        print=lambda *args: None,  # Suppress aiohttp startup banner
    )


if __name__ == "__main__":
    main()
