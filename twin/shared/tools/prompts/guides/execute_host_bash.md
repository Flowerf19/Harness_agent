<tool_description>
LEGACY Linux-only Bash Executor; dùng `host_system` cho host interaction bình thường.
</tool_description>

## execute_host_bash

Legacy Linux-only Bash Executor. Tool này được giữ tạm để tương thích demo cũ;
host interaction bình thường phải đi qua `host_system` và System Gateway.

### Khi nên dùng

- Chỉ khi maintainer/dev đang cần dùng đường legacy Linux Bash Executor.
- Không dùng làm lựa chọn mặc định cho host/Docker/log/service.

### Khi không nên dùng

- Host interaction bình thường: dùng `host_system`.
- Tính toán: dùng `run_python_code`.
- Lệnh trong sandbox hoặc phân tích dữ liệu dự án: dùng `run_python_code` với kernel bash.
- Lệnh nguy hiểm hoặc thay đổi cấu hình khi user không yêu cầu rõ.



### Input

- `command`: lệnh bash dạng plain text, không bọc markdown fence.
- `timeout`: 5-120 giây, mặc định 30.

### Quy tắc an toàn

- Không dùng sudo.
- Không đề xuất `rm -rf`, `shutdown`, `reboot`, `iptables`, hoặc lệnh phá hủy dữ liệu.
- Giới hạn output bằng `head`, `tail`, `--no-pager` khi phù hợp.
- Nếu executor chưa sẵn sàng, báo user cần khởi động Bash Executor.
