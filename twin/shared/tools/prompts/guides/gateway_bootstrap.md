<tool_description>
gateway_bootstrap — Quy trình agent hướng dẫn owner cài System Gateway khi chưa cài. Áp dụng KHI GatewayMonitor báo MISSING hoặc `gateway_admin doctor` trả `missing`.
</tool_description>

## gateway_bootstrap

Quy trình cho Evernight khi System Gateway **chưa cài / không phản hồi**. Đây là
flow "first install" hoặc "cài lại sau khi gỡ". Gateway là host boundary duy
nhất nên agent KHÔNG thể tự cài — agent chỉ hướng dẫn owner chạy 1 lệnh trên host.

### Khi nào áp dụng

- `gateway_admin status` / `doctor` báo `MISSING` (poll `/health` fail liên tục).
- Owner hỏi "cài gateway", "setup máy mới", "tại sao host_system không chạy được".
- CHỈ áp dụng khi gateway chưa sẵn sàng. Nếu đã `healthy` → KHÔNG dùng phần này.

### Nguyên tắc then chốt (BẮT BUỘC)

1. **Không tự cài.** Bootstrap do owner chạy trên HOST (không trong container).
   Agent chỉ trình bày lệnh, không chạy thay, không dùng `host_system` để cài
   (vòng lẩn quẩn: host_system cần gateway đang chạy).
2. **Lệnh gửi owner là output nguyên xi từ tool.** Gọi `gateway_admin install`
   (hoặc `install_hint`), copy **nguyên xi** code block tool trả về. Không bịa
   command, không tự ghép pip/curl/systemctl — bootstrap đã được gói vào
   `scripts/bootstrap_system_gateway.py` (chạy được trên Linux/macOS/Windows).
3. **`cd` phải là repo root chạy được.** Tool chỉ đưa path tuyệt đối khi
   `SYSTEM_GATEWAY_BOOTSTRAP_REPO_ROOT` trỏ tới repo root mà Evernight verify
   được (`scripts/bootstrap_system_gateway.py` và `services/system_gateway/`).
   Nếu không verify được, tool dùng placeholder `/path/to/march7`; khi đó nhắc
   owner thay placeholder bằng repo root thật trên host. Không đoán path.
4. **Script tự lo secret.** `bootstrap_system_gateway.py` tự sinh/đồng bộ
   shared secret: nếu `.env` đã có `SYSTEM_GATEWAY_SHARED_SECRET` → ghi vào
   `/etc/system-gateway/secret` (hoặc tương đương theo OS); nếu chưa có → sinh
   secret mới, ghi cả 2 nơi, và báo owner restart Docker stack để agent nạp lại.
   Agent KHÔNG yêu cầu owner tự ghi secret thủ công.

### Quy trình (làm theo thứ tự)

**Bước 1 — Xác nhận trạng thái.** Gọi `gateway_admin doctor`.
- Trả `missing` → tiếp tục.
- Trả `healthy`/`degraded` → KHÔNG bootstrap; báo owner trạng thái thật.

**Bước 2 — Kiểm tra repo path trong hint.** Đọc lệnh `cd` trong output
`install_hint` (gọi `gateway_admin install_hint` trước nếu cần xem). Nếu là
`/path/to/march7`, đó là placeholder vì Evernight không verify được path host;
đừng đoán path, chỉ nhắc owner thay bằng repo root thật trước khi chạy.

**Bước 3 — Trình bày lệnh bootstrap.** Gọi `gateway_admin install`. Trình bày
cho owner **nguyên xi** code block trả về (về cơ bản là 2 lệnh: `cd <repo>` +
`python3 scripts/bootstrap_system_gateway.py` trên Linux/macOS, hoặc
`python scripts\bootstrap_system_gateway.py` trong Administrator shell trên
Windows). Kèm ghi chú: "Chạy trên HOST, KHÔNG chạy trong container. Linux cần
quyền quản trị nhưng script tự re-exec sudo; Windows cần Administrator shell."
Không rút gọn, không tự thêm bước.

**Bước 4 — Xác minh.** Sau khi owner báo chạy xong, gọi lại `gateway_admin
doctor` để confirm `healthy`. Nếu vẫn `missing` → dùng bảng troubleshooting.

### Troubleshooting (báo owner, không tự fix)

| Triệu chứng | Gợi ý cho owner |
|-------------|-----------------|
| `cd /path/to/march7` trong hint | Thay placeholder bằng repo root thật trên host, hoặc set `SYSTEM_GATEWAY_BOOTSTRAP_REPO_ROOT` tới path mà Evernight/container nhìn thấy và verify được |
| `/health` trả 401/empty sau khi start | secret file host ≠ `SYSTEM_GATEWAY_SHARED_SECRET` trong `.env` → chạy lại `bootstrap_system_gateway.py` để đồng bộ, hoặc kiểm tra bằng `sudo cat /etc/system-gateway/secret` |
| Agent log `not reachable at host.docker.internal:8380` | gateway bind `127.0.0.1` → đảm bảo `SYSTEM_GATEWAY_HOST=0.0.0.0`; compose cần `extra_hosts: host.docker.internal:host-gateway` |
| `permission denied … docker.sock` | `sudo usermod -aG docker $USER` + re-login |
| `Unit system-gateway.service not found` | chưa chạy `bootstrap_system_gateway.py` đến bước install |
| Port 8380 đã chiếm | `ss -tlnp \| grep 8380`; đổi `SYSTEM_GATEWAY_PORT` đồng bộ `.env` + render unit |
| Windows: không có background service | chạy `python -m system_gateway run` foreground, hoặc dùng NSSM/Scheduled Task |

### Chống hallucination output

- Mọi command gửi owner phải có nguồn gốc từ `gateway_admin install`/`install_hint`.
  Trích "Output từ tool:" để owner phân biệt với phần nhận xét.
- Nếu output tool trống/lạ/thiếu → báo owner, không bịa command đắp vào.
- Không tự suy ra lệnh thay thế (pip/curl/systemctl) ngoài output tool — bootstrap
  đã được gói gọn trong script.
