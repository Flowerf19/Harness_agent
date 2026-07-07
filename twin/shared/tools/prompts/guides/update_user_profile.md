<tool_description>
update_user_profile — Append một bullet ổn định vào hồ sơ Core Memory T3 của user (tên, nghề, liên hệ, sở thích, thói quen, rules). Không dùng cho persona bot (đó là `update_personality`).

Khi nên dùng:
- User cung cấp thông tin bền vững: tên, nghề nghiệp, địa điểm sống, liên hệ, mối quan hệ, sở thích, thói quen, preference lâu dài, rule riêng.
- Cần lưu một cập nhật profile rõ ràng.
</tool_description>

## update_user_profile

Append một bullet ổn định vào hồ sơ Core Memory T3 của user.

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
