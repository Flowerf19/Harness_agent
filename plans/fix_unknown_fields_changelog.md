# Changelog: Fix "Unknown Fields" Issue

## Ngày: 2026-03-06

## Mô tả vấn đề
Các trường thông tin trong hệ thống relationship bị "unknown", bao gồm:
- `real_name` và `display_name` của người dùng bị null
- `relationship_type` bị "unknown" trong một số trường hợp

## Nguyên nhân đã xác định

### 1. Thiếu thông tin người dùng
- Hàm `process_message` trong `RelationshipService` chỉ truyền `username` mà không truyền `display_name` và `real_name` cho tác giả tin nhắn.
- File: `src/services/relationship/relationship_service.py` (dòng 94)

### 2. Fallback relationship type mặc định là "unknown"
- Khi LLM response không hợp lệ hoặc regex không match rõ ràng, hệ thống fallback về `"unknown"`.
- File: `src/services/relationship/bond_service.py`

## Các thay đổi đã thực hiện

### 1. Sửa hàm `process_message` để truyền đầy đủ thông tin người dùng
**File**: `src/services/relationship/relationship_service.py`

```python
# Trước:
def process_message(self, author_id, author_username, ...):
    self.update_user_name(author_id, author_username)

# Sau:
def process_message(self, author_id, author_username, ..., author_display_name=None, author_real_name=None):
    self.update_user_name(author_id, author_username, author_display_name, author_real_name)
```

### 2. Cập nhật cogs để truyền thông tin đầy đủ
**File**: `src/cogs/llm_message.py`

```python
# Lấy thông tin đầy đủ của tác giả
author_display_name = message.author.display_name if message.author.display_name != message.author.name else None
author_global_name = message.author.global_name if hasattr(message.author, "global_name") else None

# Truyền vào process_message
await self.relationship_service.process_message(
    user_id, author_username, content, mentioned_user_ids, channel_id,
    author_display_name, author_global_name
)
```

### 3. Tối ưu hóa regex patterns cho relationship detection
**File**: `src/services/relationship/bond_service.py`

- Thêm nhiều regex patterns mới cho các loại mối quan hệ: family, colleague, classmate, acquaintance
- Mỗi pattern có confidence score riêng
- Loại bỏ logic "unknown" mặc định, thay bằng "acquaintance" khi không xác định rõ

### 4. Thêm hàm `_normalize_relationship_type`
**File**: `src/services/relationship/bond_service.py`

```python
VALID_RELATIONSHIP_TYPES = {
    "friend": ["friend", "bạn", "bạn bè", "buddy", ...],
    "family": ["family", "gia đình", "anh em", ...],
    "crush": ["crush", "thích", "thầm thích", ...],
    # ...
}

def _normalize_relationship_type(self, rel_type: str) -> str:
    # Normalize và map các alias về standard type
```

### 5. Cải thiện xử lý LLM response
**File**: `src/services/relationship/bond_service.py`

- Cập nhật prompt để yêu cầu LLM không sử dụng "unknown"
- Thêm các loại relationship type mới: family, acquaintance, colleague, classmate
- Sử dụng `_normalize_relationship_type` để normalize kết quả từ LLM

### 6. Thêm validation cho relationship data
**File**: `src/services/relationship/bond_service.py`

- Validate inputs trong `_add_relationship`
- Skip self-relationship
- Normalize confidence value (0.0-1.0)
- Validate context là string

### 7. Thêm logging chi tiết
**File**: `src/services/relationship/bond_service.py`, `src/services/relationship/relationship_service.py`

- Log khi user ID là None hoặc không tìm thấy
- Log khi fallback regex không xác định được type
- Log khi relationship type là "unknown"

## Kết quả mong đợi

1. **Không còn "Unknown User"**: Khi người dùng gửi tin nhắn, thông tin `display_name` và `global_name` sẽ được lưu vào `user_names.json`

2. **Giảm đáng kể relationship type "unknown"**: 
   - Regex patterns mới có thể detect nhiều loại mối quan hệ hơn
   - LLM prompt yêu cầu không dùng "unknown"
   - Hàm normalize sẽ map về loại phù hợp nhất

3. **Dữ liệu sạch hơn**: Validation trong `_add_relationship` đảm bảo không có dữ liệu không hợp lệ

## Cách kiểm tra

1. Chạy bot và gửi tin nhắn trong kênh Discord
2. Kiểm tra file `src/data/relationships/user_names.json` - các trường `display_name` và `real_name` không còn null
3. Kiểm tra file `src/data/relationships/relationships.json` - các relationship_type không còn "unknown"
4. Sử dụng lệnh `/relationship` để xem thông tin mối quan hệ

## Files đã sửa

1. `src/services/relationship/relationship_service.py`
2. `src/cogs/llm_message.py`
3. `src/services/relationship/bond_service.py`