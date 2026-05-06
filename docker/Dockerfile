# ==========================================
# Stage 1: Builder
# ==========================================
FROM python:3.11-slim AS builder

# Cài đặt uv siêu tốc
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /build
COPY requirements.txt .

# Định nghĩa môi trường ảo multi-platform
ENV VIRTUAL_ENV=/opt/gateway_env

# Tạo venv và cài đặt package bằng uv (tận dụng cache layer)
RUN uv venv $VIRTUAL_ENV
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --python $VIRTUAL_ENV --no-cache-dir -r requirements.txt

# ==========================================
# Stage 2: Runtime (Siêu nhẹ & Bảo mật)
# ==========================================
FROM python:3.11-slim

# Cài đặt các thư viện hệ thống tối thiểu cần thiết
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl tzdata \
    && rm -rf /var/lib/apt/lists/*

# Tạo non-root user (march7_user) để tăng bảo mật
RUN useradd -m -r march7_user
WORKDIR /app

# Copy môi trường đã build từ stage 1 sang và cấu hình PATH
ENV VIRTUAL_ENV=/opt/gateway_env
COPY --from=builder $VIRTUAL_ENV $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Copy source code và set quyền sở hữu cho March7
COPY --chown=march7_user:march7_user . .

# Tạo thư mục cache cho HuggingFace với quyền của march7_user
RUN mkdir -p /app/.cache/huggingface && chown -R march7_user:march7_user /app/.cache

# Chuyển quyền thực thi
USER march7_user

ENV PYTHONPATH=/app

# Điều hướng trực tiếp bằng shell
CMD ["python", "-m", "gateway"]
