<tool_description>


## search_memory

Tìm lịch sử user trong bộ nhớ timeline T2 trên Redis.

### Khi nên dùng

- User hỏi về lịch sử, sở thích, thói quen, nội dung đã từng nói.
- User dùng từ tham chiếu như "hôm trước", "lúc nãy", "ta đã nói", "nhớ không".
- Cần tìm memory theo topic_id hoặc khoảng thời gian.

### Khi không nên dùng

- Thông tin hiện tại trên web: dùng `web_search`.
- Nội dung nằm ngay trong context hiện tại: trả lời trực tiếp.
- Hồ sơ T3 ổn định: dùng `get_profile`.
</tool_description>

### Input

- `user_id` bắt buộc là Discord ID dạng số. Dùng CURRENT USER hoặc MENTIONED USERS từ system prompt.
- `mode`: `auto`, `semantic`, `time`, `topic`, `recent`.
- `query`: bắt buộc cho semantic; viết cụ thể, không dùng "chuyện đó".
- `topic_id` hoặc `topic`: bắt buộc cho topic.
- `hours`/`days`: dùng cho time/recent.
- `limit`: mặc định 5, tối đa 20.

### Lỗi cần tránh

- Không đoán user_id theo tên hiển thị.
- Không dùng semantic với query mơ hồ; nếu user nói "lúc nãy" hãy dùng time/recent.
