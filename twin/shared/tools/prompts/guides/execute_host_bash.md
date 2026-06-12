<tool_description>
Khi cần kiểm tra host, Docker, log, service, hoặc chạy bash thật.


## execute_host_bash

Chạy lệnh bash trên máy host của bot thông qua Bash Executor. Mỗi lần gọi đều cần người dùng duyệt.

### Khi nên dùng

- Kiểm tra host: `sensors`, `free -h`, `df -h`, `docker ps`, `docker logs`, `systemctl status`, `tail` log.
- User nói rõ muốn xem trạng thái máy hoặc chạy lệnh trên host.

### Khi không nên dùng

- Tính toán: dùng `run_python_code`.
- Lệnh trong sandbox hoặc phân tích dữ liệu dự án: dùng `run_python_code` với kernel bash.
- Lệnh nguy hiểm hoặc thay đổi cấu hình khi user không yêu cầu rõ.

</tool_description>

### Input

- `command`: lệnh bash dạng plain text, không bọc markdown fence.
- `timeout`: 5-120 giây, mặc định 30.

### Quy tắc an toàn

- Không dùng sudo.
- Không đề xuất `rm -rf`, `shutdown`, `reboot`, `iptables`, hoặc lệnh phá hủy dữ liệu.
- Giới hạn output bằng `head`, `tail`, `--no-pager` khi phù hợp.
- Nếu executor chưa sẵn sàng, báo user cần khởi động Bash Executor.
