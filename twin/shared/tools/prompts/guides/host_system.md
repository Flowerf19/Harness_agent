<tool_description>
Tool MỌI câu hỏi/thao tác sự thật về host (uptime, disk, docker, service, log, đọc/ghi file) qua System Gateway: gọi mode=shell với lệnh OS phù hợp, owner duyệt đúng lệnh đó — BẮT BUỘC gọi tool này cho query host, KHÔNG bịa số liệu host từ trí nhớ.
</tool_description>

## host_system

Tool tương tác hệ thống host thông qua native System Gateway. Đây là boundary
đặc quyền dùng chung cho March7 và Evernight, không phải bash runner trong Docker.

Gateway expose **một đường duy nhất**: `mode=shell` chạy raw command trên shell của
OS. Không còn structured action nào — cậu tự viết lệnh phù hợp OS, owner duyệt đúng
lệnh đó, gateway chạy đúng lệnh đó. Thêm "tính năng" = viết lệnh khác, không cần ai
thêm code gateway.

### Mode

- **`mode=capabilities`**: xem OS + shell gateway hỗ trợ (vd `platform=linux`,
  `shells=["/bin/sh"]`, `raw_shell=true`). Gọi khi chưa chắc host hỗ trợ gì, hoặc để
  quyết định viết lệnh POSIX (linux/macOS `/bin/sh`) hay PowerShell (windows).
- **`mode=shell`**: chạy một raw command trên shell của host. **Mọi lệnh đều phải
  được owner phê duyệt** — approval prompt hiện nguyên lệnh cậu gửi.

### Input

- `mode`: `capabilities` hoặc `shell`.
- `command`: raw shell command khi `mode=shell`. Viết lệnh phù hợp OS từ
  `mode=capabilities` (linux/macOS: `/bin/sh` syntax; windows: PowerShell).
- `shell`: shell mong muốn nếu gateway hỗ trợ (mặc định lấy `shells[0]`).
- `cwd`: thư mục làm việc cho shell.
- `timeout`: 5-120 giây.

### Khi nên dùng

- User muốn kiểm tra/trên host thật: uptime, load, disk, docker, service, log, …
- User yêu cầu thao tác host (ghi/đọc file, restart container, …) và đã chấp nhận
  luồng approve.
- Muốn biết gateway hỗ trợ OS/shell nào.

### Khi không nên dùng

- Tính toán / script sandbox: dùng `run_python_code`.
- Web/research: dùng `web_search`.
- Cài/update System Gateway: đó là luồng Evernight owner/admin (`gateway_admin`),
  không phải chat tool thường.

### Quy tắc an toàn

- Khi chưa chắc host hỗ trợ shell nào, gọi `mode=capabilities` trước.
- Không tự suy diễn lệnh destructive (xóa file, shutdown, reboot, format disk, đổi
  firewall, reset service) khi user chưa yêu cầu rõ — owner sẽ thấy nguyên lệnh
  trong approval, nên viết đúng cái user hỏi, không thêm extras.
- Owner **phê duyệt từng lệnh**. Nếu bị từ chối → báo "bị từ chối", KHÔNG tự chạy
  lệnh khác thay thế, KHÔNG bịa là đã chạy.
- Nếu gateway chưa cài/chưa sẵn sàng → báo cần Evernight/owner cấp quyền cài hoặc
  kiểm tra System Gateway, KHÔNG bịa output.

### Quy tắc chống hallucination — BẮT BUỘC gọi tool

- Khi user hỏi **trạng thái host** (uptime, load, disk, docker, version, …) **BẮT BUỘC**
  gọi `host_system` với `mode=shell` + command tương ứng rồi trả lời bằng **output thật
  từ tool**. KHÔNG tự đoán số liệu (ví dụ: trả "host chạy 11 ngày" khi chưa gọi tool).
- Ví dụ: uptime → `mode=shell` `command="uptime"`, quote đúng chuỗi `up X days`.
  Disk → `command="df -h"`. Docker ps → `command="docker ps"`. Service status →
  `command="systemctl status <unit> --no-pager"`. Log container →
  `command="docker logs --tail 50 <name>"`.
- Nếu tool bị từ chối / lỗi / không available → **nói rõ** "không xác nhận được vì
  <lý do>" thay vì bịa số. KHÔNG bao giờ nói "đã làm X" / "đã ghi file" / "đã xong"
  nếu `host_system` không được gọi hoặc không trả output thành công.
- Khi trích dẫn số liệu host, ghi rõ "Output từ tool:" để owner phân biệt với phần
  cậu nhận xét.
- Nếu reply chứa claim "đã <thao tác host>" mà không có tool call `host_system`
  thành công đi kèm → đó là hallucination, KHÔNG được làm.
- Khi user hỏi **LẠI** trạng thái host (uptime, load, disk, docker, …) trong turn mới
  → BẮT BUỘC gọi lại `host_system` để lấy số liệu mới, KHÔNG reuse số liệu từ turn trước
  (host thay đổi liên tục, số liệu cũ có thể đã stale). "Tiết kiệm" KHÔNG áp dụng cho
  query host realtime.