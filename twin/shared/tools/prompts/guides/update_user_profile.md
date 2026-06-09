<tool_description>
Khi cần lưu thông tin bền vững của user vào hồ sơ T3.
</tool_description>

## update_user_profile

Append một bullet ổn định vào hồ sơ Core Memory T3 của user.

### Khi nên dùng

- User cung cấp thông tin bền vững: tên, nghề nghiệp, địa điểm sống, liên hệ, mối quan hệ, sở thích, thói quen, preference lâu dài, rule riêng.
- Cần lưu một cập nhật profile rõ ràng.

### Khi không nên dùng

- Tâm trạng hoặc nhu cầu một lần.
- Guess/suy diễn chưa được xác nhận.
- Nội dung cần ghi đè toàn bộ profile: không dùng tool này.

### Input

- `user_id`: Discord ID dạng số của người mà thông tin nói tới.
- `section`: một trong `basic`, `contact`, `relationship`, `work`, `interest`, `habit`, `psychological`, `rules`.
- `content`: một bullet sạch, không prefix `- `, viết tiếng Việt.
- `source_memory_id`: optional nếu thông tin đến từ T2.

### Quy tắc

- Mỗi call chỉ append một thông tin.
- Nếu conflict với profile cũ, append thông tin mới; cleanup sẽ merge/supersede sau.
- Nếu chưa chắc section, đọc `get_profile` hoặc hỏi lại.
