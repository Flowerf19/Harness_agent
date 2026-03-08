# Sử dụng image Python 3.11 bản slim để tối ưu dung lượng
FROM python:3.11-slim

# Thiết lập thư mục làm việc bên trong container
WORKDIR /app

# Cài đặt các thư viện hệ thống cơ bản (Cần thiết nếu máy tính ảo cần compile một số package Python)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Sao chép file requirements.txt vào trước để tận dụng Docker Cache
COPY requirements.txt .

# Cài đặt PyTorch với ROCm support (cho AMD GPU)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/rocm6.2

# Cài đặt các thư viện Python còn lại
RUN pip install --no-cache-dir -r requirements.txt

# Sao chép toàn bộ mã nguồn dự án vào container
COPY . .

# Thiết lập các biến môi trường mặc định cho Phoenix Tracker
# Dùng host.docker.internal để bot trong container có thể thấy Phoenix ở máy host
ENV PHOENIX_COLLECTOR_ENDPOINT="http://host.docker.internal:4317"
ENV PHOENIX_PROJECT_NAME="Be_Bay_Bot"

# Khai báo thư mục gốc để Python có thể import các module trong src/ đúng cách
ENV PYTHONPATH=/app

# Lệnh khởi động Bot
CMD ["python", "src/bot.py"]