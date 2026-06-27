<tool_description>
Viết lại file persona của bot. Tool tự route sang IDENTITY.md hoặc SOUL.md và sẽ overwrite file mục tiêu.
</tool_description>

## update_personality

Viết lại file persona của bot. Tool tự route sang IDENTITY.md hoặc SOUL.md và sẽ overwrite file mục tiêu.

### Khi nên dùng

- User yêu cầu đổi identity, tính cách, vai trò, cách xưng hô, phong cách nói, emoji, hoặc độ dài câu trả lờitrực trực tiếp.
- Yêu cầu rõ ràng là thay đổi bot/persona, không phải profile user.

### Khi không nên dùng

- User nói về sở thích/thông tin của chính họ: dùng `update_user_profile`.
- Chỉ cần trả lờitrực trực tiếp câu hỏi thông thường.



### Input

- `instruction`: toàn bộ nội dung Markdown mới cho file mục tiêu. Phải merge nội dung cũ nếu muốn giữ.

### Quy tắc

- Đây là overwrite, không append.
- Nên đọc/bảo tồn nội dung hiện có nếu user chỉ yêu cầu sửa một phần.
- Auto-route: identity keywords vào IDENTITY.md; style/speech keywords vào SOUL.md.
