# HƯỚNG DẪN SỬ DỤNG TOOL

## Quick Reference

| Tool | Khi dùng | Query style |
|------|----------|-------------|
| `search_memory` | Chuyện cũ, sở thích, info đã chat | **CỤ THỂ**: topic, tên, category |
| `web_search` | Tin mới, thời tiết, giá, tin tức | Keyword + "hôm nay", "giá", "tin tức" |
| `update_user_profile` | Info MỚI về user (tên, quê, sở thích) | 1 fact rõ ràng |
| `update_personality` | User YÊU CẦU thay đổi bot | Full Markdown content |

---

## search_memory (Tìm ký ức T2)

### 3 Search Modes

| Mode | Khi dùng | Parameters |
|------|----------|------------|
| `semantic` (default) | Tìm nội dung, sở thích, facts | `query="..."` |
| `time` | Tìm chuyện gần đây | `days=7` |
| `topic` | Tìm theo tên topic chính xác | `topic="anime"` |

### Mode: semantic (default)

**Khi dùng:** Tìm nội dung, sở thích, facts dựa trên meaning.

**Query phải CỤ THỂ:**

**❌ KHÔNG:** Query chung chung
- "nãy đã nói" → FAIL
- "chuyện cũ" → FAIL
- "cái đó" → FAIL

**✅ ĐÚNG:** Extract keywords từ tin nhắn
- User: "nãy tui nói đang xem anime gì?" → `query="anime đang xem"`
- User: "sở thích của tui là gì?" → `query="sở thích"`
- User: "tui thích game nào?" → `query="game sở thích"`

**VD:**
```
search_memory(user_id="123", query="anime sở thích")
search_memory(user_id="123", mode="semantic", query="crush relationship")
```

### Mode: time

**Khi dùng:** "hôm qua nói gì", "tuần này", "gần đây".

**VD:**
```
search_memory(user_id="123", mode="time", days=7)  # 7 ngày qua
search_memory(user_id="123", mode="time", days=30) # 30 ngày qua
```

**User nói → Mode:**
- "hôm qua tui nói gì" → `mode="time", days=1`
- "tuần này có gì không" → `mode="time", days=7`
- "gần đây có gì mới" → `mode="time", days=7`

### Mode: topic

**Khi dùng:** Tìm theo tên topic (keyword match trong `canonical_topic`).

**VD:**
```
search_memory(user_id="123", mode="topic", topic="anime")     # Tất cả topics có "anime"
search_memory(user_id="123", mode="topic", topic="game")      # Tất cả topics có "game"
search_memory(user_id="123", mode="topic", topic="crush")     # Tất cả topics có "crush"
```

**Lưu ý:** Topic search là keyword match, không phải semantic. Kết quả được sort theo importance descending.

### Quick Decision Flowchart

```
User hỏi về:
├─ "hôm qua", "gần đây", "tuần này" → mode="time"
├─ Topic cụ thể (anime, game, crush) → mode="topic"
└─ Nội dung, sở thích, facts → mode="semantic" (default)
```

### Wiki Page structure (để query đúng)

Wiki pages được chunk theo TOPIC, mỗi page có:
- `canonical_topic`: snake_case (VD: "Evangelion_Anime", "Sở_thích_game")
- `category`: entertainment, relationship, work_study, casual, daily_mood
- `current_summary`: Nội dung chính
- `key_points`: List facts cụ thể
- `importance`: 1-5 (quan trọng)
- `last_updated`: timestamp (dùng cho time mode)

### Cách semantic search hoạt động

**Embedding:** `canonical_topic + current_summary + key_points` được embed → semantic search
**Query match:** Query có thể match với topic name, summary, hoặc individual facts

**Query TỐT:**
- Descriptive phrases: `"anime đang xem Evangelion"` → match summary
- Topic + context: `"game sở thích"` → match summary
- Specific facts: `"episode nào"` → match key_points `"watching ep 14"`

**Query KÉM:**
- Too vague: `"nãy đã nói"` → không match với bất kỳ content

---

## web_search (Tìm tin tức real-time)

### Khi dùng
- Thời tiết, giá, tin tức
- Sự kiện đang diễn ra
- Info ngoài training data

### Khi KHÔNG dùng
- Sở thích, info user đã chat → dùng `search_memory`
- Knowledge general (VD: "Python là gì") → không cần tool

### Query examples
- `"thời tiết Hà Nội hôm nay"`
- `"giá Bitcoin hiện tại"`
- `"tin tức AI 2024"`
- `"review phim Evangelion"` (chưa xem)

---

## update_user_profile (Cập nhật T3 Core Memory)

### Khi dùng
- User chia sẻ info MỚI chắc chắn:
  - Tên, nickname: "Tên tui là Hoàng"
  - Quê: "Tui ở Phú Thọ"
  - Sở thích: "Tui thích chơi Dota"
  - Công việc: "Tui làm dev"

### Khi KHÔNG dùng
- Info đã biết → không update lại
- Info mơ hồ: "có thể", "chắc là", "hình như"
- Info tạm: "hôm nay buồn", "đang ăn"

### Fact format
```
"Tên là Hoàng"         ✅
"Sở thích chơi Dota"   ✅
"Quê Phú Thọ"          ✅
"chắc là tui thích..." ❌ (mơ hồ)
```

---

## update_personality (Viết lại IDENTITY/SOUL)

### ⚠️ OVERWRITE toàn bộ file
Bot phải:
1. Đọc content cũ từ system prompt
2. Merge với yêu cầu mới
3. Provide FULL Markdown content

### Auto-routing
- Keywords: tên, tính cách, backstory → IDENTITY.md
- Keywords: nói, ngắn, emoji, style → SOUL.md

### CHỈ dùng khi user YÊU CẦU
- "Bot nói ngắn hơn" → update SOUL.md
- "Bot tên là ABC" → update IDENTITY.md
- KHÔNG tự ý thay đổi

---

## Decision Flowchart

```
User nhắc chuyện cũ?
├─ Yes → search_memory (query cụ thể)
└─ No → User hỏi tin mới?
    ├─ Yes → web_search
    └─ No → User chia sẻ info cá nhân?
        ├─ Yes → update_user_profile
        └─ No → User yêu cầu thay đổi bot?
            ├─ Yes → update_personality
            └─ No → Không cần tool
```

---

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| `search_memory(query="nãy đã nói")` | Extract: `"anime"` hoặc `"game"` |
| `web_search` cho info đã chat | Dùng `search_memory` |
| `update_user_profile` cho info biết | Không update, dùng已有的 |
| Generic query không match topic | Add category keyword: `"anime entertainment"` |