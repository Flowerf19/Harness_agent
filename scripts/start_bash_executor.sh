#!/bin/bash
# ==========================================
# Bash Executor - Start Script
# ==========================================
# Khởi động Bash Executor trên host.
#
# Usage:
#   chmod +x scripts/start_bash_executor.sh
#   ./scripts/start_bash_executor.sh
# ==========================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Load config from .env.bash_executor if exists
if [ -f ".env.bash_executor" ]; then
    export $(grep -v '^#' .env.bash_executor | xargs)
fi

# Defaults
export BASH_EXECUTOR_HOST="${BASH_EXECUTOR_HOST:-127.0.0.1}"
export BASH_EXECUTOR_PORT="${BASH_EXECUTOR_PORT:-8374}"
export PYTHONPATH="${PROJECT_DIR}:${PYTHONPATH}"

echo "Starting Bash Executor on ${BASH_EXECUTOR_HOST}:${BASH_EXECUTOR_PORT}..."
exec python3 -m src.server.bash_executor
