# Bash Executor — Hướng Dẫn Sử Dụng

## Tổng quan

Bash Executor là service chạy trên host, cho phép **March7 Agent** thực thi lệnh bash trên máy của bạn. Agent có thể kiểm tra nhiệt độ, RAM, disk, quản lý Docker, đọc log, restart service...

**Mỗi lần agent muốn chạy lệnh, bạn sẽ nhận được popup xác nhận trên Discord.**

---

## ⚠️ CẢNH BÁO BẢO MẬT - ĐỌC KỸ TRƯỚC KHI CÀI

| Rủi ro | Mức độ | Chi tiết |
|--------|--------|----------|
| **Prompt injection** | **CAO** | Kẻ tấn công có thể lừa agent chạy `rm -rf /`, `shutdown`, xóa container |
| **Lộ dữ liệu** | Trung bình | Agent có thể đọc file `.env`, token, cấu hình |
| **Resource exhaustion** | Trung bình | Fork bomb, chiếm CPU/RAM |
| **Privilege escalation** | Thấp | Service chạy non-root nên giới hạn quyền |

### Biện pháp bảo vệ (đã có trong code)

- **ApprovalGate**: Mọi lệnh đều log và yêu cầu xác nhận
- **Non-root user**: Service chạy dưới user thường, không có sudo
- **Origin validation**: Chỉ container gateway/agent được phép gọi
- **Timeout**: Mỗi lệnh tối đa 120 giây
- **Output truncation**: Giới hạn 8000 ký tự output

### Khuyến nghị

1. **Chạy trong VM riêng** nếu có thể — tách biệt hoàn toàn với máy chính
2. **Dùng firewall** giới hạn IP được gọi port 8374: `sudo ufw allow from 172.17.0.0/16 to any port 8374`
3. **Kiểm tra log định kỳ**: `sudo journalctl -u bash-executor -f`
4. **Backup dữ liệu** trước khi bật tool này
5. **KHÔNG chạy service dưới root**

---

## Cài đặt (3 bước)

### Bước 1: Setup

```bash
cd /path/to/march7
./scripts/setup_bash_executor.sh
```

Script sẽ kiểm tra Python, cài aiohttp, tạo file `.env.bash_executor`.

### Bước 2: Cấu hình

Chỉnh sửa `.env.bash_executor` nếu cần:

```env
BASH_EXECUTOR_HOST=127.0.0.1
BASH_EXECUTOR_PORT=8374
BASH_EXECUTOR_MAX_TIMEOUT=120
```

### Bước 3: Khởi động

**Cách A - Chạy tay (để test):**

```bash
./scripts/start_bash_executor.sh
```

**Cách B - systemd (recommended):**

```bash
# 1. Sửa file service
sudo cp docker/bash-executor.service /etc/systemd/system/
sudo nano /etc/systemd/system/bash-executor.service
# Sửa: User=YOUR_USERNAME, WorkingDirectory=/path/to/march7

# 2. Khởi động
sudo systemctl daemon-reload
sudo systemctl enable --now bash-executor

# 3. Kiểm tra
sudo systemctl status bash-executor
sudo journalctl -u bash-executor -f
```

---

## Kiểm tra

Sau khi Bash Executor chạy:

```bash
# Health check
curl http://localhost:8374/health
# → {"status": "ok", "uptime": 42}

# Test chạy lệnh
curl -H 'Origin: march7-bot' \
  -X POST http://localhost:8374/execute \
  -H 'Content-Type: application/json' \
  -d '{"command": "echo hello world", "timeout": 10}'
# → {"stdout": "hello world\n", "stderr": "", "exit_code": 0}

# Test bảo mật (phải bị từ chối)
curl -H 'Origin: evil.com' \
  -X POST http://localhost:8374/execute \
  -H 'Content-Type: application/json' \
  -d '{"command": "whoami"}'
# → 403 Forbidden
```

### Test với agent

Chat với Bé Bảy trên Discord:

- "kiểm tra RAM máy" → agent gọi `free -h`
- "docker đang chạy gì" → agent gọi `docker ps`
- "nhiệt độ CPU" → agent gọi `sensors` (cần cài `lm-sensors`)

---

## Các lệnh an toàn để test

| Lệnh | Kết quả |
|------|---------|
| `echo hello` | In "hello" |
| `date` | Ngày giờ hiện tại |
| `df -h` | Dung lượng disk |
| `free -h` | RAM available |
| `uptime` | Thời gian host đã chạy |
| `docker ps` | Container đang chạy |
| `sensors` | Nhiệt độ CPU |
| `systemctl status nginx` | Trạng thái service |

---

## Gỡ cài đặt

```bash
sudo systemctl stop bash-executor
sudo systemctl disable bash-executor
sudo rm /etc/systemd/system/bash-executor.service
sudo systemctl daemon-reload
rm -f .env.bash_executor
```

---

## Troubleshooting

### "Không kết nối được đến Bash Executor"

- Kiểm tra service đang chạy: `curl http://localhost:8374/health`
- Kiểm tra firewall: port 8374 có mở không?
- Từ container: `curl http://host.docker.internal:8374/health`

### "Forbidden: Origin not allowed"

- Kiểm tra header `Origin: march7-bot` có trong request không
- Kiểm tra `BASH_EXECUTOR_ALLOWED_ORIGINS` trong `.env.bash_executor`

### "Command timed out"

- Tăng `BASH_EXECUTOR_MAX_TIMEOUT` trong `.env.bash_executor`
- Lệnh kéo dài quá lâu, thử chạy lệnh nhẹ hơn
