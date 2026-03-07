# Kế hoạch sửa lỗi "các trường bị unknown"

## Phân tích vấn đề

Sau khi phân tích codebase và dữ liệu, đã xác định được 2 nguyên nhân chính:

### Nguyên nhân 1: Thiếu thông tin người dùng
- Các trường `real_name` và `display_name` trong `user_names.json` đều là `null`
- Hệ thống chỉ thu thập `username` từ Discord, không lấy thông tin đầy đủ về người dùng
- Khi hiển thị thông tin người dùng, hệ thống không có dữ liệu chi tiết để hiển thị

### Nguyên nhân 2: Fallback relationship type mặc định
- Khi LLM response không hợp lệ hoặc regex không match rõ ràng, hệ thống fallback về `"unknown"`
- Logic fallback hiện tại quá đơn giản, không có cơ chế suy luận tốt hơn

## Giải pháp đề xuất

### 1. Cải thiện thu thập thông tin người dùng

**Mục tiêu**: Tự động thu thập và cập nhật thông tin đầy đủ về người dùng từ Discord API.

**Các bước thực hiện**:
- Sửa đổi hàm `update_user_name` trong `BondService` để lấy thêm thông tin từ Discord member object
- Thêm khả năng trích xuất real_name từ nội dung tin nhắn (khi người dùng tự giới thiệu)
- Cập nhật logic `_get_user_display_name` để ưu tiên thông tin có sẵn

**File cần sửa**:
- `src/services/relationship/bond_service.py`
- `src/cogs/base_cog.py` (nơi gọi update_user_name)

### 2. Tối ưu hóa relationship type detection

**Mục tiêu**: Giảm thiểu việc sử dụng "unknown" bằng cách cải thiện logic fallback và xử lý LLM response.

**Các bước thực hiện**:
- Cải thiện regex patterns để nhận diện nhiều loại mối quan hệ hơn
- Thêm cơ chế suy luận dựa trên ngữ cảnh khi không thể xác định rõ ràng
- Cải thiện xử lý JSON từ LLM response với các kỹ thuật robust hơn
- Thêm validation tốt hơn cho dữ liệu relationship

**File cần sửa**:
- `src/services/relationship/bond_service.py`
- `src/services/relationship/relationship_service.py`

### 3. Cải thiện xử lý LLM response

**Mục tiêu**: Giảm tỷ lệ fallback bằng cách xử lý LLM response tốt hơn.

**Các bước thực hiện**:
- Thêm retry mechanism khi LLM response không hợp lệ
- Cải thiện prompt để LLM trả về JSON có cấu trúc rõ ràng hơn
- Thêm validation và cleanup cho LLM response trước khi parse

## Thứ tự ưu tiên

1. **Ưu tiên cao**: Cải thiện thu thập thông tin người dùng (giải quyết vấn đề gốc rễ)
2. **Ưu tiên trung bình**: Tối ưu hóa relationship type detection  
3. **Ưu tiên thấp**: Cải thiện xử lý LLM response (tùy chọn nếu vẫn còn vấn đề sau 2 bước trên)

## Tiêu chí thành công

- Không còn xuất hiện "Unknown User" trong hiển thị thông tin người dùng
- Giảm đáng kể số lượng relationship type = "unknown" 
- Hệ thống có thể hiển thị thông tin người dùng đầy đủ (real_name, display_name khi có sẵn)
- Logging không còn cảnh báo về missing user info hoặc unknown relationship types