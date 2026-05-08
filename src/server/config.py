"""
Configuration for Bash Executor server.

Reads from environment variables with sensible defaults.
"""

import os


class BashExecutorConfig:
    """Config for Bash Executor standalone HTTP server."""

    HOST = os.getenv("BASH_EXECUTOR_HOST", "127.0.0.1")
    PORT = int(os.getenv("BASH_EXECUTOR_PORT", "8374"))
    ALLOWED_ORIGINS = os.getenv(
        "BASH_EXECUTOR_ALLOWED_ORIGINS",
        "march7-bot,http://localhost:8374,http://host.docker.internal:8374",
    ).split(",")
    MAX_OUTPUT_CHARS = int(os.getenv("BASH_EXECUTOR_MAX_OUTPUT_CHARS", "8000"))
    DEFAULT_TIMEOUT = int(os.getenv("BASH_EXECUTOR_DEFAULT_TIMEOUT", "30"))
    MAX_TIMEOUT = int(os.getenv("BASH_EXECUTOR_MAX_TIMEOUT", "120"))
