# Kế hoạch sửa lỗi hệ thống ba lớp bộ nhớ

## Phân tích vấn đề từ log

Từ log được cung cấp, có thể xác định các vấn đề chính:

1. **Treo khóa (Lock timeout)**: 
   - Dòng log: `2026-02-27 00:12:41,365 - WARNING - ⚠️ Auto-releasing lock for user 1378359549379084432 after 30s timeout`
   - Người dùng `1378359549379084432` bị treo khóa trong hơn 30 giây, khiến hệ thống phải tự động giải phóng

2. **Spam detection**: 
   - Dòng log: `2026-02-27 00:12:42,340 - WARNING - 🚫 User 726302130318868500 spam detected! 30s cooldown`
   - Người dùng `726302130318868500` gửi nhiều tin nhắn liên tiếp về việc thêm mối quan hệ, gây ra cảnh báo spam

3. **Quản lý mối quan hệ**: 
   - Có nhiều tin nhắn liên quan đến việc thêm mối quan hệ giữa các người dùng

## Các vấn đề chính đã xác định

### 1. Cơ chế khóa không an toàn
- Hàm `_process_ai_response` trong `LLMMessageCog` có thể gặp lỗi giữa chừng mà không giải phóng khóa
- Thiếu cơ chế đảm bảo khóa luôn được giải phóng trong mọi trường hợp

### 2. Thiếu xử lý ngoại lệ đầy đủ
- Nếu có lỗi xảy ra trong quá trình xử lý tin nhắn, khóa có thể không được giải phóng
- Một số lỗi có thể làm treo toàn bộ luồng xử lý

### 3. Cơ chế timeout chưa tối ưu
- Dù đã có cơ chế tự động giải phóng khóa sau 30s, nhưng vẫn có thể xảy ra trường hợp ngoại lệ
- Cần có cơ chế timeout kép để đảm bảo an toàn

### 4. Cơ chế chống spam cần tinh chỉnh
- Người dùng có thể gửi nhiều tin nhắn về mối quan hệ hợp lệ nhưng bị coi là spam
- Cần phân biệt giữa spam và hành vi hợp lệ

## Giải pháp đề xuất

### 1. Cải thiện cơ chế khóa an toàn
```python
async def _process_ai_response(self, message, content: str, user_id: str):
    """Process AI response using 3-tier memory system with safe locking"""
    lock_released = False
    try:
        # Lock conversation with timeout
        self._set_conversation_lock(user_id)
        
        # Use MemoryManager to get comprehensive context
        context = self.memory_manager.get_context(user_id)
        
        # ... xử lý nội dung ...
        
        # Add both user message and bot response to memory system
        self.memory_manager.add_message(user_id, "user", content)
        self.memory_manager.add_message(user_id, "assistant", response)
        
    except asyncio.CancelledError:
        logger.warning(f"⚠️ AI response processing cancelled for user {user_id}")
        raise  # Re-raise to properly handle cancellation
    except Exception as e:
        logger.error(f"❌ Error processing AI response: {e}")
        try:
            await message.reply("Xin lỗi, đã có lỗi xảy ra khi tạo phản hồi.")
        except:
            pass
    finally:
        # Always release lock in a safe way
        if not lock_released:
            try:
                self._release_conversation_lock()
                lock_released = True
            except Exception as e:
                logger.error(f"❌ Error releasing conversation lock: {e}")
```

### 2. Cải thiện xử lý ngoại lệ
- Đảm bảo mọi lỗi đều được bắt và xử lý đúng cách
- Sử dụng cấu trúc try-finally để đảm bảo tài nguyên luôn được giải phóng
- Thêm cơ chế retry cho các thao tác quan trọng

### 3. Tinh chỉnh cơ chế chống spam
- Phân biệt giữa tin nhắn về mối quan hệ và spam thực sự
- Điều chỉnh ngưỡng spam để phù hợp với hành vi người dùng
- Có thể thêm cơ chế phân loại nội dung để giảm cảnh báo sai

## Triển khai

### Bước 1: Cải thiện hàm `_process_ai_response`
- Thêm cấu trúc try-finally để đảm bảo khóa luôn được giải phóng
- Cải thiện xử lý ngoại lệ

### Bước 2: Cập nhật cơ chế khóa
- Thêm cơ chế timeout kép để đảm bảo an toàn
- Cải thiện cơ chế theo dõi khóa

### Bước 3: Tinh chỉnh chống spam
- Cập nhật ngưỡng spam
- Thêm logic phân biệt loại tin nhắn

### Bước 4: Kiểm thử
- Kiểm thử với các kịch bản khác nhau
- Đảm bảo không còn hiện tượng treo khóa
- Kiểm tra hiệu suất và độ ổn định

## Kết quả mong đợi

- Không còn hiện tượng treo khóa kéo dài
- Hệ thống xử lý tin nhắn ổn định hơn
- Giảm số lượng cảnh báo spam sai
- Cải thiện trải nghiệm người dùng