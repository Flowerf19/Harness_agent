# Plan: Nút Khởi Động Bash Executor Khi Tool Fail

## Yêu cầu

Khi bot gọi `execute_host_bash` mà Bash Executor trên host (port 8374) không chạy:
1. Hiện Discord message với nút **[🚀 Khởi động]** (có cảnh báo: "bot sẽ có quyền truy cập hệ thống máy host")
2. Khi click → bot tự động start service trên host qua HTTP endpoint
3. Tự retry lệnh thất bại

## Kiến trúc

```
Discord ──► DiscordGatewayHandler ──► ChatCoordinator ──► MCPClient ──► ToolRegistry ──► ExecuteHostBashTool
                  ▲                                                                              │
                  │                                BashExecutorUnavailableError ◄────────────────┘
                  │                                                                              
                  ├─► Gửi nút [Khởi động] [Hủy]                                                  
                  ├─► User click [Khởi động] → HTTP POST host.docker.internal:8375/start         
                  ├─► Retry ChatCoordinator.process_message()                                    
                  └─► Gửi kết quả cho user                                                        
```

**Nguyên tắc:**
- `BashExecutorUnavailableError` là exception đặc biệt, không bị ChatCoordinator nuốt → propagate thẳng lên handler
- Handler bắt được → dừng agent loop, hiện UI chờ tương tác, retry toàn bộ

## Các File Cần Sửa/Tạo

### 1. Exception mới: `src/services/tools/exceptions.py`
Thêm `BashExecutorUnavailableError(ToolExecutionError)` với field `executor_url`.

### 2. Sửa: `src/services/tools/implementations/execute_host_bash_tool.py`
`_call_executor()`: `aiohttp.ClientConnectionError` → raise `BashExecutorUnavailableError` thay vì return error dict.
Import exception mới.

### 3. Sửa: `src/services/chat_coordinator.py`
Vòng lặp tool trong `process_message()`: thêm `except BashExecutorUnavailableError: raise` để exception propagate lên handler.
Import exception mới.

### 4. Sửa: `gateway/adapters/discord/handler.py`
- `handle_message()`: bắt `BashExecutorUnavailableError`, gọi `_handle_bash_executor_unavailable(raw_message, user_id, content)`
- Thêm `_handle_bash_executor_unavailable()`: tạo `BashExecutorStartView`, gửi Discord message
- Thêm `retry_process_message(raw_message, user_id, content)`: gọi lại coordinator + gửi response

### 5. File mới: `gateway/adapters/discord/views/bash_executor_start.py`
Discord View (`discord.ui.View`) timeout 30s:
- Nút **[🚀 Khởi động]** (green): `POST http://host.docker.internal:8375/start` → đợi 2s → `handler.retry_process_message()`
- Nút **[❌ Hủy]** (gray): báo "Đã hủy", disable buttons
- Xử lý lỗi starter: nếu starter cũng fail → báo lỗi + hướng dẫn chạy thủ công `systemctl --user start bash-executor`

### 6. File mới: `scripts/bash_executor_starter.py`
Tiny aiohttp HTTP server port 8375:
- `POST /start`: validate Origin "march7-bot" → `subprocess.run(["systemctl", "--user", "start", "bash-executor"])` → return JSON status
- `GET /health`: return uptime

### 7. File mới: `docker/bash-executor-starter.service`
systemd user unit, luôn chạy, auto-start on boot:
```ini
[Unit]
Description=March7 Bash Executor Starter
[Service]
Type=simple
User=flowerf
WorkingDirectory=/home/flowerf/Projects/march7
ExecStart=/usr/bin/python3 scripts/bash_executor_starter.py
Restart=on-failure
[Install]
WantedBy=multi-user.target
```

### 8. Sửa: `docker/bash-executor.service`
Fix placeholder → `User=flowerf`, `WorkingDirectory=/home/flowerf/Projects/march7`, `EnvironmentFile=/home/flowerf/Projects/march7/.env.bash_executor`, `Environment=PYTHONPATH=/home/flowerf/Projects/march7`

### 9. Kiểm tra: `docker/docker-compose.bot.yml`
Đã có `extra_hosts: host.docker.internal:host-gateway` → container gọi được port 8375 qua host.

## Không Đụng
- `ApprovalGate` — giữ nguyên auto-approve, nút Approve làm task sau
- `MCPServer`, `MCPClient`, `MCPTransport`, `ToolRegistry` — không đụng

## Luồng Hoạt Động

1. User gửi message → Handler gọi Coordinator → LLM muốn dùng execute_host_bash
2. Tool gọi HTTP → không kết nối được → raise BashExecutorUnavailableError
3. Exception propagate qua Coordinator → Handler
4. Handler gửi Discord: "⚠️ Host tool chưa khởi động. Nếu khởi động, bot có quyền truy cập hệ thống máy host. Bạn muốn khởi động?" + 2 nút
5. Click [Khởi động] → POST starter → systemctl start → đợi 2s → retry process_message → gửi kết quả
6. Click [Hủy] / timeout → báo hủy

## Verification

1. `systemctl --user stop bash-executor`
2. Gửi lệnh Discord yêu cầu host tool → nút hiện ra
3. Click [Khởi động] → service start → retry OK
4. Click [Hủy] → báo hủy
5. Reboot → starter tự chạy, sẵn sàng
