<tool_description>
Evernight-only: curate T3 profile với hash conflict protection. Hai chế độ: một-section (truyền 'section'+'bullets') hoặc toàn-file (bỏ 'section', truyền 'sections' map). Cần `expected_profile_hash` từ `get_profile` — LUÔN gọi `get_profile` trước để đọc hồ sơ + hash, rồi mới curate.
</tool_description>

## manage_user_profile

Curate hồ sơ T3. Tool này là destructive/curation, chỉ dùng cho Evernight.

- Chế độ một-section: truyền `section` + `bullets`, thay toàn bộ bullet của đúng một section.
- Chế độ toàn-file: bỏ trống `section`, truyền `sections` map (section->bullets) để ghi đè cả hồ sơ trong một call. Map là authoritative: section vắng mặt trong map sẽ bị xóa sạch.

### Khi nên dùng

- Cleanup duplicate hoặc bullet cũ không còn đúng.
- Delete, merge, rewrite, hoặc resolve conflict trong hồ sơ T3.
- Cần giữ section canonical nhưng thay nội dung của một section (một-section).
- Cần rewrite/dedup nhiều section cùng lúc (toàn-file).

### Khi không nên dùng

- Fact mới vừa xuất hiện: dùng `update_user_profile`.
- Append realtime T2->T3: dùng `update_user_profile`.
- Persona, cách nói, hoặc luật chung của bot: dùng `update_personality`.

Trước khi gọi tool này, TỰ gọi `get_profile(user_id)` để đọc nội dung hiện tại và lấy `expected_profile_hash`. KHÔNG hỏi user hash, KHÔNG bắt user chọn section — tự đọc, tự quyết, tự curate.


### Input

- `user_id`: Discord ID dạng số.
- `section`: một trong `basic`, `contact`, `relationship`, `work`, `interest`, `habit`, `psychological`, `rules`. Bỏ trống để chạy chế độ toàn-file.
- `bullets`: list bullet sạch, không prefix `- `, mỗi bullet một dòng (chế độ một-section). List rỗng nghĩa là xóa sạch section đó.
- `sections`: map `section -> [bullets]` cho chế độ toàn-file. Chỉ chứa 8 section hợp lệ; section vắng mặt sẽ bị xóa sạch.
- `allow_shrink`: boolean (mặc định false). Chế độ toàn-file tự chặn nếu rewrite làm mất >50% bullet của hồ sơ không tầm thường; đặt `true` để cố ý dedup mạnh.
- `expected_profile_hash`: SHA256 của raw profile hiện tại lấy từ `get_profile`.
- `reason`: lý do cleanup/delete/merge/rewrite/conflict.

### Quy tắc

- Chế độ một-section: một call chỉ xử lý một section.
- Chế độ toàn-file: `sections` là authoritative — phải gửi đủ bullet muốn giữ ở mọi section, vì section vắng mặt sẽ bị xóa.
- Nếu tool báo conflict, đọc lại `get_profile`, kiểm tra thay đổi mới, rồi gọi lại với hash mới nếu vẫn cần curate.
- Nếu tool báo mất >50% bullet, kiểm tra lại nội dung; chỉ đặt `allow_shrink=true` khi chắc chắn cố ý.
- Không dùng để lưu fact mới; fact mới đi qua hot append `update_user_profile`.
- Section `rules` là rule/preference riêng của user, không phải `RULES.md` chung của bot.
