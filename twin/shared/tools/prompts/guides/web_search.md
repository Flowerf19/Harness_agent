<tool_description>
web_search — Tìm kiếm web hiện tại qua Tavily: tin tức, thời tiết, giá, sự kiện, lịch, phiên bản mới, thông tin có thể thay đổi — dùng khi user cần "mới nhất", "hôm nay", "cập nhật", hoặc cần nguồn web.
Khi nên dùng:
- Tin tức, lịch, giá, phiên bản mới, sự kiện hiện tại, thông tin có thể thay đổi.
- User yêu cầu "mới nhất", "hôm nay", "cập nhật", hoặc cần nguồn web.
</tool_description>

## web_search

Tìm kiếm web hiện tại qua Tavily.

### Input

- `query` bắt buộc; thêm năm hiện tại hoặc từ khóa recency nếu cần.
- `search_depth`: `basic` mặc định, `advanced` khi cần sâu hơn.
- `max_results`: 1-10, thường 3-5.
- `topic`: `news` cho tin nóng, `general` cho còn lại.
- `time_range`: `day`, `week`, `month`, `year` khi cần giới hạn thời gian.
- `include_domains`/`exclude_domains` khi user yêu cầu nguồn cụ thể.

### Quy tắc

- Tin tức nên dùng `topic="news"` và `time_range="week"` nếu không có range khác.
- Sau khi có kết quả, tóm tắt theo nguồn; không bịa ngoài result.
