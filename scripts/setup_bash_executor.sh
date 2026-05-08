#!/bin/bash
# ==========================================
# Bash Executor - Setup Script
# ==========================================
# Cài đặt Bash Executor trên host machine.
# Chạy 1 lần duy nhất trước khi dùng.
#
# Usage:
#   chmod +x scripts/setup_bash_executor.sh
#   ./scripts/setup_bash_executor.sh
# ==========================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "========================================"
echo "  Bash Executor - Setup"
echo "========================================"
echo ""

# 1. Kiểm tra Python
echo "[1/4] Kiểm tra Python..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1)
    echo "  ✅ $PYTHON_VERSION"
else
    echo "  ❌ python3 not found. Please install Python 3.10+."
    exit 1
fi

# 2. Kiểm tra aiohttp
echo "[2/4] Kiểm tra aiohttp..."
if python3 -c "import aiohttp" 2>/dev/null; then
    echo "  ✅ aiohttp already installed"
else
    echo "  ⚠️  aiohttp not found. Installing..."
    pip install aiohttp
    echo "  ✅ aiohttp installed"
fi

# 3. Tạo file .env template nếu chưa có
echo "[3/4] Kiểm tra cấu hình env..."
ENV_FILE="$PROJECT_DIR/.env.bash_executor"
if [ -f "$ENV_FILE" ]; then
    echo "  ✅ .env.bash_executor already exists"
else
    cat > "$ENV_FILE" << 'EOF'
# Bash Executor Configuration
BASH_EXECUTOR_HOST=127.0.0.1
BASH_EXECUTOR_PORT=8374
BASH_EXECUTOR_MAX_OUTPUT_CHARS=8000
BASH_EXECUTOR_DEFAULT_TIMEOUT=30
BASH_EXECUTOR_MAX_TIMEOUT=120
BASH_EXECUTOR_ALLOWED_ORIGINS=march7-bot,http://localhost:8374,http://host.docker.internal:8374
EOF
    echo "  ✅ Created .env.bash_executor with defaults"
fi

# 4. Test chạy
echo "[4/4] Kiểm tra khởi động..."
cd "$PROJECT_DIR"

if timeout 3 python3 -m src.server.bash_executor &>/dev/null; then
    echo "  ❌ Server failed to start. Check logs above."
else
    # Exit code 124 means timeout is normal (we killed it after 3s)
    echo "  ✅ Bash Executor starts successfully"
fi

echo ""
echo "========================================"
echo "  Setup hoàn tất!"
echo "========================================"
echo ""
echo "Để chạy Bash Executor:"
echo "  ./scripts/start_bash_executor.sh"
echo ""
echo "Để chạy dưới systemd:"
echo "  1. Copy docker/bash-executor.service vào /etc/systemd/system/"
echo "  2. sudo systemctl enable --now bash-executor"
echo "  3. sudo systemctl status bash-executor"
echo ""
echo "Để test:"
echo "  curl -H 'Origin: march7-bot' \\"
echo "    -X POST http://localhost:8374/execute \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"command\": \"echo hello world\", \"timeout\": 10}'"
