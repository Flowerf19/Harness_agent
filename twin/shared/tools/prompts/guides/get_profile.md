<tool_description>
get_profile — Đọc hồ sơ T3 ổn định của user (tên, nghề, liên hệ, sở thích, thói quen, rules). Gọi TRƯỚC khi curate/`manage_user_profile` để lấy `expected_profile_hash`. Không dùng để đọc persona/SOUL.md/IDENTITY.md/system prompt của bot — đó là `update_personality`.
Khi nên dùng:
- Cần biết chính xác hồ sơ hiện có trước khi trả lời hoặc trước khi append thông tin mới.
- User hỏi về thông tin ổn định của họ: tên, công việc, liên hệ, sở thích, hoặc rules.
</tool_description>

## get_profile

Đọc hồ sơ Markdown T3 ổn định của user.

### Input

- `user_id` bắt buộc là Discord ID dạng số.
- `section` optional: `basic`, `contact`, `relationship`, `work`, `interest`, `habit`, `psychological`, `rules`.

### Lỗi cần tránh

- Không dùng username thay cho ID số.
- Không gọi nếu chỉ cần lưu một thông tin mới và đã đủ section/content: dùng `update_user_profile`.
