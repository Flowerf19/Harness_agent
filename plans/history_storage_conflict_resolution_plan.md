# Kế hoạch Giải quyết Xung đột Lưu trữ Lịch sử

## Vấn đề Hiện tại
Hệ thống có 2 services cùng lưu lịch sử vào file `{user_id}_history.json` với định dạng khác nhau:

- **ConversationManager**: Lưu với timestamp, role "assistant", giới hạn 100 tin nhắn
- **HistoryService**: Lưu không có timestamp, role "bot", giới hạn 50 tin nhắn

Cả hai services đang hoạt động đồng thời → ghi đè lẫn nhau → dữ liệu bị hỏng.

## Phân tích Sử dụng Thực tế
- **LLM Message Cog** → sử dụng ConversationManager (luồng chính xử lý tin nhắn)
- **Memory Manager** → sử dụng HistoryService (hệ thống quản lý bộ nhớ)

## Giải pháp Đề xuất
**Giữ lại ConversationManager, loại bỏ HistoryService** vì:
- ConversationManager có thiết kế tốt hơn (timestamp, chuẩn role)
- Được sử dụng trong luồng xử lý chính
- HistoryService gây xung đột dữ liệu

## Các bước Thực hiện

### Bước 1: Tạo Script Migration Dữ liệu
- [ ] Viết script `migrate_history_format.py` để chuẩn hóa tất cả file history
- [ ] Xử lý các trường hợp:
  - Tin nhắn có timestamp → giữ nguyên
  - Tin nhắn không có timestamp → thêm timestamp dựa trên thứ tự hoặc thời gian file
  - Chuẩn hóa role "bot" → "assistant"
- [ ] Backup tất cả file history trước khi migration
- [ ] Test script trên dữ liệu mẫu

### Bước 2: Cập nhật MemoryManager
- [ ] Sửa `src/services/memory_manager.py` để sử dụng ConversationManager thay vì HistoryService
- [ ] Thêm phương thức mới vào ConversationManager nếu cần để hỗ trợ use case của MemoryManager
- [ ] Cập nhật dependency injection trong MemoryManager

### Bước 3: Loại bỏ HistoryService
- [ ] Xóa hoặc deprecate HistoryService
- [ ] Cập nhật tất cả imports liên quan
- [ ] Cập nhật tests nếu có

### Bước 4: Cập nhật ConversationManager (nếu cần)
- [ ] Đảm bảo ConversationManager hỗ trợ đầy đủ các tính năng cần thiết cho MemoryManager
- [ ] Thêm logging chi tiết để theo dõi quá trình ghi lịch sử
- [ ] Xem xét tăng giới hạn lịch sử nếu cần (hiện tại 100 là hợp lý)

### Bước 5: Testing và Verification
- [ ] Test migration script với dữ liệu thực tế
- [ ] Test hệ thống sau khi cập nhật với nhiều user đồng thời
- [ ] Verify format consistency của file history
- [ ] Kiểm tra không có race condition khi ghi file

## Rủi ro Tiềm ẩn

### 1. Data Loss Risk
- **Rủi ro**: Dữ liệu lịch sử có thể bị mất trong quá trình migration
- **Giải pháp**: 
  - Backup tất cả file trước khi migration
  - Test script migration kỹ lưỡng trên môi trường staging
  - Implement rollback mechanism

### 2. Race Condition
- **Rủi ro**: Nhiều tiến trình ghi file history cùng lúc có thể gây corruption
- **Giải pháp**:
  - Thêm file locking khi ghi file
  - Sử dụng atomic write operations
  - Xem xét chuyển sang database nếu scale lớn

### 3. Breaking Changes
- **Rủi ro**: Các thành phần khác phụ thuộc vào HistoryService có thể bị ảnh hưởng
- **Giải pháp**:
  - Audit toàn bộ codebase để tìm dependencies
  - Cập nhật tất cả chỗ sử dụng HistoryService
  - Test end-to-end toàn bộ hệ thống

### 4. Performance Impact
- **Rủi ro**: Ghi file với timestamp có thể chậm hơn
- **Giải pháp**:
  - Monitor performance sau khi deploy
  - Xem xét async write nếu cần

## Cách Test/Verify

### 1. Data Migration Testing
- [ ] Tạo dataset test với các trường hợp:
  - File history chỉ có ConversationManager format
  - File history chỉ có HistoryService format  
  - File history bị xung đột (cả hai format)
  - File history rỗng
- [ ] Chạy migration script và verify output format chuẩn

### 2. Integration Testing
- [ ] Test gửi tin nhắn từ Discord bot
- [ ] Verify file history được ghi đúng format (có timestamp, role "assistant")
- [ ] Test với nhiều user đồng thời
- [ ] Test giới hạn 100 tin nhắn hoạt động đúng

### 3. Regression Testing
- [ ] Đảm bảo các tính năng hiện tại vẫn hoạt động:
  - Lấy lịch sử trò chuyện
  - Tạo summary user
  - Working memory
  - Background processing

### 4. Monitoring
- [ ] Thêm logging để theo dõi quá trình ghi file
- [ ] Monitor error rates sau khi deploy
- [ ] Theo dõi kích thước file history

## Timeline Ước lượng
- **Migration script**: 1-2 ngày
- **Code changes**: 2-3 ngày  
- **Testing**: 2-3 ngày
- **Deploy và monitoring**: 1-2 ngày

## Rollback Plan
- Nếu có vấn đề nghiêm trọng:
  1. Restore từ backup files
  2. Revert code changes
  3. Temporarily disable HistoryService để tránh xung đột
  4. Investigate và fix root cause

## Success Criteria
- [ ] Tất cả file history có format chuẩn (timestamp + role "assistant")
- [ ] Không có lỗi ghi file trong logs
- [ ] Hệ thống xử lý tin nhắn bình thường
- [ ] Dữ liệu lịch sử được preserve đầy đủ
- [ ] Performance không bị ảnh hưởng đáng kể