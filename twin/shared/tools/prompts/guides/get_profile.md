<tool_description>
Khi cần đọc hồ sơ T3 ổn định của user.
</tool_description>

## get_profile

Đọc hồ sơ Markdown T3 ổn định của user.

### Khi nên dùng

- Cần biết chính xác hồ sơ hiện có trước khi trả lời hoặc trước khi append thông tin mới.
- User hỏi về thông tin ổn định của họ: tên, công việc, liên hệ, sở thích, hoặc rules.

### Khi không nên dùng

- Cần tìm hội thoại quá khứ: dùng `search_memory`.
- User vừa cung cấp thông tin ngay trong context: có thể trả lời trực tiếp.

### Input

- `user_id` bắt buộc là Discord ID dạng số.
- `section` optional: `basic`, `contact`, `relationship`, `work`, `interest`, `habit`, `psychological`, `rules`.

### Lỗi cần tránh

- Không dùng username thay cho ID số.
- Không gọi nếu chỉ cần lưu một thông tin mới và đã đủ section/content: dùng `update_user_profile`.
