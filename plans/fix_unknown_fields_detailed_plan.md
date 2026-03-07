# Kế hoạch sửa lỗi "các trường bị unknown" - Chi tiết kỹ thuật

## Vấn đề đã xác định

### Vấn đề 1: Thiếu thông tin người dùng cho tác giả tin nhắn
- **Nguyên nhân**: Trong hàm `process_message` của `RelationshipService`, chỉ gọi `update_user_name(author_id, author_username)` mà không truyền `display_name` và `real_name`.
- **Hệ quả**: Các trường `display_name` và `real_name` trong `user_names.json` luôn là `null` cho tác giả tin nhắn.
- **Vị trí code**: `src/services/relationship/relationship_service.py` dòng 94

### Vấn đề 2: Fallback relationship type mặc định là "unknown"
- **Nguyên nhân**: Logic fallback regex quá đơn giản, không có cơ chế suy luận tốt hơn khi không thể xác định rõ ràng loại mối quan hệ.
- **Hệ quả**: Nhiều mối quan hệ có type = "unknown", làm giảm chất lượng dữ liệu.

## Giải pháp kỹ thuật

### Fix 1: Cập nhật hàm process_message để truyền đầy đủ thông tin

**Các bước thực hiện**:

1. **Mở rộng signature hàm `process_message`**:
   ```python
   async def process_message(
       self,
       author_id: str,
       author_username: str,
       message_content: str,
       mentioned_user_ids: Optional[List[str]] = None,
       channel_id: Optional[str] = None,
       author_display_name: Optional[str] = None,
       author_real_name: Optional[str] = None,
   ):
   ```

2. **Cập nhật logic update_user_name**:
   ```python
   # Update author's name info with full details
   self.update_user_name(
       author_id, 
       author_username, 
       author_display_name, 
       author_real_name
   )
   ```

3. **Cập nhật cogs để truyền thông tin đầy đủ**:
   Trong `src/cogs/llm_message.py`, thay vì chỉ truyền `author_username`, cần truyền cả `display_name` và `global_name`.

### Fix 2: Cải thiện logic relationship type detection

**Các bước thực hiện**:

1. **Mở rộng regex patterns** để nhận diện nhiều ngữ cảnh hơn
2. **Thêm cơ chế suy luận dựa trên confidence score** từ LLM
3. **Cải thiện xử lý JSON response** với các kỹ thuật robust hơn

### Fix 3: Thêm khả năng trích xuất real_name từ nội dung tin nhắn

**Các bước thực hiện**:

1. **Thêm pattern regex** để detect tự giới thiệu: "tên tôi là X", "tôi là X", "gọi tôi là X", v.v.
2. **Tích hợp vào hệ thống xử lý tin nhắn** để tự động cập nhật real_name

## Thứ tự triển khai

1. **Ưu tiên cao**: Fix vấn đề thiếu thông tin người dùng (sửa hàm process_message và cogs)
2. **Ưu tiên trung bình**: Cải thiện relationship type detection  
3. **Ưu tiên thấp**: Thêm trích xuất real_name từ nội dung

## Tiêu chí kiểm thử

- [ ] Kiểm tra file `user_names.json` sau khi gửi tin nhắn: các trường `display_name` và `real_name` không còn là `null`
- [ ] Kiểm tra lệnh `/relationship`: không còn hiển thị "Unknown User"
- [ ] Kiểm tra relationship types: giảm đáng kể số lượng "unknown"
- [ ] Logging không còn cảnh báo về missing user info