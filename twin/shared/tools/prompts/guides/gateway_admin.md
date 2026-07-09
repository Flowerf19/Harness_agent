<tool_description>
gateway_admin — Owner-only System Gateway administration. Use when the owner asks about gateway status, wants diagnosis, needs the bootstrap install command, or requests an update.

Khi nên dùng:
- Owner hỏi trạng thái System Gateway.
- Owner muốn chẩn đoán gateway có healthy không.
- Owner muốn cài gateway lần đầu / cài lại (bootstrap).
- Owner cần lệnh bootstrap để chạy trên host.
- Owner yêu cầu update gateway.
</tool_description>

## gateway_admin

Tool quản trị System Gateway dành riêng cho owner. Không dùng cho user thường.

### Input

- `command`: `status`, `doctor`, `install_hint`, `install`, `update`.
- `target_version`: phiên bản mục tiêu khi `command=update`.
- `install_path`: thư mục cài March7 trên host, hoặc path tới
  `scripts/bootstrap_system_gateway.py`, khi `command=install/install_hint`.

### Quy tắc an toàn

- Tool từ chối nếu caller không phải owner.
- Không tự động cài hoặc update nếu owner chưa yêu cầu rõ.
- `install` chỉ trả bootstrap command do code sinh ra để owner tự chạy trên host.
  KHÔNG nhận shell command do model/user viết.
- Nếu owner đã đưa thư mục cài March7 hoặc path `scripts/bootstrap_system_gateway.py`,
  truyền nguyên path đó vào `install_path`; tool tự cắt về project root.
- `install_hint` chỉ cung cấp command để owner tự chạy trên host; không chạy thay owner.

### Quy tắc chống hallucination output

- Khi tool trả về **code block / shell command** (đặc biệt `install_hint`, `update`),
  copy code block từ tool. Không tự suy ra command khác (ví dụ: `find /...`,
  `npx ...`, `pip install ...`, `curl | bash ...`).
- Nếu output trông bất thường hoặc thiếu, **báo lại cho owner** thay vì bịa command.
- Khi trích dẫn, ghi rõ "Output từ tool:" để owner phân biệt với phần cậu nhận xét.

### Khi Gateway chưa cài / không phản hồi (MISSING)

Khi `status`/`doctor` báo `missing`, BẮT BUỘC làm theo quy trình bootstrap dưới
đây để hướng dẫn owner cài trên host. Agent KHÔNG tự cài được (vòng lẩn quẩn:
`host_system` cần gateway đang chạy). Quy trình đầy đủ (hỏi repo path, khớp
trình bày lệnh nguyên xi, xác minh) nằm ở guide được include bên dưới:

@include gateway_bootstrap.md
