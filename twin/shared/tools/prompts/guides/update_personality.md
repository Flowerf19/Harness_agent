<tool_description>
Đổi persona, cách nói, hoặc luật chung của bot; không dùng cho hồ sơ user.
</tool_description>

## update_personality

Viết lại file persona/rules của bot. Tool overwrite toàn bộ file mục tiêu; bạn phải tự chọn `target_file`.

### Khi nên dùng

- User yêu cầu đổi identity, tính cách, vai trò, cách xưng hô, phong cách nói, icon/emoji, độ dài câu trả lời, hoặc luật hành vi của bot.
- Yêu cầu rõ ràng là thay đổi bot/persona, không phải profile user.

### Khi không nên dùng

- User nói về sở thích/thông tin của chính họ: dùng `update_user_profile`.
- Chỉ cần trả lời trực tiếp câu hỏi thông thường.

### Input

- `instruction`: toàn bộ nội dung Markdown mới cho file mục tiêu. Phải merge nội dung cũ nếu muốn giữ.
- `target_file`: tên file cần ghi, không phải path.
  - `RULES.md`: luật chung được nạp cho cả March7 và Evernight.
  - `IDENTITY.md`: danh tính/nhân vật của bot hiện tại.
  - `SOUL.md`: cách nói riêng của bot hiện tại.
  - Một file `.md` khác trong persona dir của bot hiện tại, nếu file đó tồn tại hoặc user yêu cầu tạo rõ ràng.

### Quy tắc

- Đây là overwrite, không append.
- Nên đọc/bảo tồn nội dung hiện có nếu user chỉ yêu cầu sửa một phần.
- Luôn truyền `target_file`; tool không tự chọn file thay bạn.
- Chọn file theo ý nghĩa:
  - Đổi danh tính, vai trò, xưng hô cốt lõi, lore/nhân vật → `IDENTITY.md`.
  - Đổi giọng riêng, slang/icon, độ dài, phong cách trả lời riêng của bot → `SOUL.md`.
  - Đổi luật chung áp dụng cho cả hai bot, format cấm, `[skip]`, tool/data rules → `RULES.md`.
- `RULES.md` là shared rules: sửa file này sẽ ảnh hưởng cả hai bot sau khi process tương ứng reload/restart. Bot hiện tại reload ngay sau tool call.
