#!/usr/bin/env python3
"""
Bash Executor Starter - HTTP endpoint để bot gọi start bash executor.

Chạy trên host (port 8375), luôn on qua systemd.
Bot trong Docker container gọi POST /start qua host.docker.internal:8375
để khởi động bash executor service.

Không dùng aiohttp web.run_app() vì cần tương thích systemd simple type.
"""

import logging
import subprocess
import sys
from aiohttp import web

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("bash-executor-starter")

STARTER_PORT = 8375
ALLOWED_ORIGIN = "march7-bot"


async def handle_health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def handle_start(request: web.Request) -> web.Response:
    origin = request.headers.get("Origin", "")
    if origin.strip() != ALLOWED_ORIGIN:
        logger.warning(f"Rejected request from origin: {origin}")
        raise web.HTTPForbidden()

    logger.info("Starting bash executor via systemctl...")
    try:
        result = subprocess.run(
            ["systemctl", "--user", "start", "bash-executor"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        success = result.returncode == 0
        logger.info(
            f"systemctl start bash-executor: rc={result.returncode} "
            f"stdout={result.stdout.strip()!r} stderr={result.stderr.strip()!r}"
        )
        return web.json_response({
            "status": "started" if success else "failed",
            "rc": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        })
    except subprocess.TimeoutExpired:
        logger.error("systemctl start timed out")
        return web.json_response({"status": "timeout"}, status=500)
    except FileNotFoundError:
        logger.error("systemctl not found")
        return web.json_response({"status": "failed", "error": "systemctl not found"}, status=500)


app = web.Application()
app.router.add_get("/health", handle_health)
app.router.add_post("/start", handle_start)


if __name__ == "__main__":
    logger.info(f"Bash Executor Starter listening on 0.0.0.0:{STARTER_PORT}")
    web.run_app(app, host="0.0.0.0", port=STARTER_PORT, print=None)
