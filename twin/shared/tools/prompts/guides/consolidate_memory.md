<tool_description>
consolidate_memory — Tổng hợp tin nhắn gần đây thành timeline summary (T2) và cập nhật profile (T3).

Khi nên dùng:
- Nhận A2A request từ March7 khi T1 tràn (token threshold)
- User đã chat nhiều (>20 messages) và cần lưu thông tin quan trọng
- Conversation sắp kết thúc hoặc user offline
</tool_description>

## consolidate_memory

Tổng hợp tin nhắn T1 thành timeline summary (T2) và cập nhật profile (T3).

### Parameters

```json
{
  "user_id": "string (required) - ID của user cần consolidate",
  "reason": "string (required) - Lý do consolidate",
  "max_messages": "integer (optional, default: 200) - Số messages tối đa"
}
```

### Kết quả trả về

```json
{
  "status": "ok",
  "timeline_summary": "Tóm tắt cuộc trò chuyện...",
  "profile_updates": {
    "work": ["Fact mới về công việc"],
    "interest": ["Sở thích mới"]
  },
  "messages_summarized": 25
}
```

### Cách đọc kết quả

- `status`: "ok" = thành công, "skipped" = không có gì đáng lưu
- `timeline_summary`: đã lưu vào T2 (timeline summaries)
- `profile_updates`: đã cập nhật T3 (profile)
- `messages_summarized`: số messages đã tóm tắt

### Lỗi thường gặp

- `"no_messages"`: T1 trống, không có gì để consolidate
- `"llm_failed"`: LLM call thất bại
- `"parse_failed"`: Không parse được JSON từ LLM response
