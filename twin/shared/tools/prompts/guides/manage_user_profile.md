<tool_description>
Evernight-only: curate, merge, delete, or rewrite exactly one T3 profile section with hash conflict protection.
## manage_user_profile

Thay toàn bộ bullet của một section T3 bằng danh sách bullet mới. Tool này là destructive/curation, chỉ dùng cho Evernight.

### Khi nên dùng

- Cleanup duplicate hoặc bullet cũ không còn đúng.
- Delete, merge, rewrite, hoặc resolve conflict trong hồ sơ T3.
- Cần giữ section canonical nhưng thay nội dung của một section.

### Khi không nên dùng

- Fact mới vừa xuất hiện: dùng `update_user_profile`.
- Append realtime T2->T3: dùng `update_user_profile`.
- Muốn sửa nhiều section trong một lần: không dùng một call duy nhất.
</tool_description>

### Input

- `user_id`: Discord ID dạng số.
- `section`: một trong `basic`, `contact`, `relationship`, `work`, `interest`, `habit`, `psychological`, `rules`.
- `bullets`: list bullet sạch, không prefix `- `, mỗi bullet một dòng. List rỗng nghĩa là xóa sạch section đó.
- `expected_profile_hash`: SHA256 của raw profile hiện tại lấy từ `get_profile`.
- `reason`: lý do cleanup/delete/merge/rewrite/conflict.

### Quy tắc

- Một call chỉ xử lý một section.
- Luôn đọc profile hiện tại trước, dùng đúng `expected_profile_hash` từ lần đọc đó.
- Nếu tool báo conflict, đọc lại `get_profile`, kiểm tra thay đổi mới, rồi gọi lại với hash mới nếu vẫn cần curate.
- Không dùng để lưu fact mới; fact mới đi qua hot append `update_user_profile`.
