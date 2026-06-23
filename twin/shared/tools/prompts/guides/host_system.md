<tool_description>
Tương tác host thật qua System Gateway theo capability; ưu tiên action có cấu trúc, raw shell chỉ khi user yêu cầu rõ.
</tool_description>

## host_system

Tool tương tác hệ thống host thông qua native System Gateway. Đây là boundary
đặc quyền dùng chung cho March7 và Evernight, không phải bash runner trong
Docker.

### Khi nên dùng

- User muốn kiểm tra trạng thái host thật: system status, disk, service, Docker.
- User muốn xem capability hiện tại của System Gateway.
- User yêu cầu rõ một thao tác host và đã chấp nhận luồng approve.

### Khi không nên dùng

- Tính toán, phân tích dữ liệu, script sandbox: dùng `run_python_code`.
- Web/research: dùng `web_search`.
- Lệnh tùy ý khi có structured action tương đương.
- Cài đặt/update System Gateway: đó là luồng Evernight owner/admin, không phải chat tool thường.

### Input

- `mode`: `capabilities`, `action`, hoặc `shell`.
- `action`: tên structured action khi `mode=action`, ví dụ `system.status`.
- `arguments`: object tham số cho action.
- `command`: raw shell command khi `mode=shell`.
- `shell`: shell mong muốn nếu gateway hỗ trợ.
- `cwd`: thư mục làm việc cho raw shell.
- `timeout`: 5-120 giây.

### Quy tắc an toàn

- Luôn gọi `mode=capabilities` khi chưa chắc host hỗ trợ feature nào.
- Ưu tiên structured action thay vì raw shell.
- Raw shell chỉ dùng khi user yêu cầu rõ và System Gateway báo `raw_shell=true`.
- Không tự suy diễn lệnh destructive như xóa file, shutdown, reboot, format disk,
  đổi firewall, hoặc reset service khi user chưa yêu cầu rõ.
- Nếu gateway chưa cài/chưa sẵn sàng, báo cần Evernight/owner cấp quyền cài
  hoặc kiểm tra System Gateway.
