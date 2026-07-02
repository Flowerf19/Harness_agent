<tool_description>
Đổi persona hoặc cách nói của chính bot; không dùng cho hồ sơ user.
</tool_description>

## update_personality

Viết lại file persona của bot hiện tại. Tool overwrite toàn bộ file mục tiêu; bạn phải tự chọn `target_file`.

### Khi nên dùng

- User yêu cầu đổi identity, tính cách, vai trò, cách xưng hô, phong cách nói, icon/emoji, độ dài câu trả lời, hoặc quy tắc hành vi của bot.
- Yêu cầu rõ ràng là thay đổi bot/persona, không phải profile user.

### Khi không nên dùng

- User nói về sở thích/thông tin của chính họ: dùng `update_user_profile`.
- Chỉ cần trả lời trực tiếp câu hỏi thông thường.

### Input

- `instruction`: toàn bộ nội dung Markdown mới cho file mục tiêu. Phải merge nội dung cũ nếu muốn giữ.
- `target_file`: tên file cần ghi, không phải path. Chỉ nhận filename (không có `/`, `\`, hay `..`).
  - `IDENTITY.md`: danh tính/nhân vật của bot hiện tại.
  - `SOUL.md`: cách nói + quy tắc hội thoại của bot hiện tại.
  - Một file `.md` khác trong persona dir của bot hiện tại, nếu file đó tồn tại hoặc user yêu cầu tạo rõ ràng.

### Chọn IDENTITY.md hay SOUL.md

- Sửa **IDENTITY.md** khi đổi *bot LÀ AI*: tên, vai trò, xuất thân/lore, ngoại hình, tính cách nền, sở thích, động lực, cách xưng hô cốt lõi (ví dụ xưng "tui" / "ta").
- Sửa **SOUL.md** khi đổi *bot NÓI THẾ NÀO*: giọng điệu, slang/icon được phép, độ dài câu trả lời, cấm markdown, quy tắc `[skip]` trong kênh chung, cách dùng USER ID, xử lý trí nhớ, quy tắc gọi tool.
- Nếu phân vân: thứ mô tả bản chất/nhân vật → IDENTITY.md; thứ chi phối phong cách trả lời từng tin nhắn → SOUL.md.

### Quy tắc

- Đây là overwrite, không append: `instruction` phải là toàn bộ nội dung file sau khi merge.
- Nên đọc/bảo tồn nội dung hiện có (`=== NHÂN CÁCH CỦA BẠN ===` cho IDENTITY, `=== HƯỚNG DẪN HỘI THOẠI ===` cho SOUL) nếu user chỉ yêu cầu sửa một phần.
- Luôn truyền `target_file`; tool không tự chọn file thay bạn.
- Tool chỉ ghi vào persona dir của bot hiện tại; thay đổi áp dụng ngay cho bot hiện tại từ tin nhắn tiếp theo (reload sau tool call).
