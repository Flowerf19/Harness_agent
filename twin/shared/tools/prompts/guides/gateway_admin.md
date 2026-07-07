<tool_description>
gateway_admin — Owner-only System Gateway administration. Use when the owner asks about gateway status, wants diagnosis, needs the bootstrap install command, or requests an update.

Khi nên dùng:
- Owner hỏi trạng thái System Gateway.
- Owner muốn chẩn đoán gateway có healthy không.
- Owner cần lệnh bootstrap để cài gateway lần đầu.
- Owner yêu cầu update gateway.
</tool_description>

## gateway_admin

Tool quản trị System Gateway dành riêng cho owner. Không dùng cho user thường.

### Input

- `command`: `status`, `doctor`, `install_hint`, `update`.
- `target_version`: phiên bản mục tiêu khi `command=update`.

### Quy tắc an toàn

- Tool từ chối nếu caller không phải owner.
- Không tự động cài hoặc update nếu owner chưa yêu cầu rõ.
- `install_hint` chỉ cung cấp command để owner tự chạy trên host; không chạy thay owner.

### Quy tắc chống hallucination output

- Khi tool trả về **code block / shell command** (đặc biệt `install_hint`, `update`),
  copy **nguyên xi** output từ tool. Không tự suy ra command khác (ví dụ: `npx ...`,
  `pip install ...`, `curl | bash ...`).
- Nếu output trông bất thường hoặc thiếu, **báo lại cho owner** thay vì bịa command.
- Khi trích dẫn, ghi rõ "Output từ tool:" để owner phân biệt với phần cậu nhận xét.
