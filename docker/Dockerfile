# Sử dụng Miniconda base image
FROM continuumio/miniconda3:latest

WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Thiết lập biến môi trường
ENV CONDA_ENV_NAME=discord_bot
ENV PYTHONPATH=/app

# Tạo entrypoint script để quản lý conda env tại runtime
RUN echo '#!/bin/bash\n\
set -e\n\
ENV_NAME="${CONDA_ENV_NAME}"\n\
ENV_PATH="/opt/conda_envs/${ENV_NAME}"\n\
\n\
# Kiểm tra xem env đã tồn tại trong volume chưa\n\
if [ -d "${ENV_PATH}" ]; then\n\
    echo "✅ Conda env '${ENV_NAME}' đã tồn tại, kiểm tra requirements..."\n\
    source activate ${ENV_PATH}\n\
    pip install --no-cache-dir -r /app/requirements.txt 2>/dev/null || true\n\
else\n\
    echo "🔨 Tạo mới conda env '${ENV_NAME}'..."\n\
    mkdir -p /opt/conda_envs\n\
    conda create --prefix ${ENV_PATH} python=3.11 -y\n\
    source activate ${ENV_PATH}\n\
    pip install --no-cache-dir -r /app/requirements.txt\n\
fi\n\
\n\
echo "🚀 Khởi động bot..."\n\
exec python src/bot.py\n\
' > /entrypoint.sh && chmod +x /entrypoint.sh

# Copy source code
COPY . .

# Mount point cho conda envs
VOLUME ["/opt/conda_envs"]

# Khởi động
CMD ["/entrypoint.sh"]