<tool_description>
Append một bullet ổn định vào hồ sơ Core Memory T3 của user.
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
- User muốn đổi persona hoặc cách nói của bot: dùng `update_personality`.



### Input

- `user_id`: Discord ID dạng số của user được đề cập.
- `section`: một trong `basic`, `contact`, `relationship`, `work`, `interest`, `habit`, `psychological`, `rules`.
- `content`: một bullet sạch, không prefix `- `, viết tiếng Việt.
- `source_memory_id`: optional nếu thông tin đến từ T2.

### Quy tắc

- Mỗi call chỉ append một thông tin.
- Nếu conflict với profile cũ, append thông tin mới; cleanup sẽ merge/supersede sau.
- Nếu chưa chắc section, đọc `get_profile` hoặc hỏi lại.
- Section `rules` là rule/preference riêng của user, không phải quy tắc/persona của bot (đó là `update_personality`).
