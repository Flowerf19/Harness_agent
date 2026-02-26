# Kế hoạch Debug chi tiết cho hệ thống 3 tầng Bộ Nhớ

## Mục tiêu
- Xác minh rằng tất cả các tầng bộ nhớ hoạt động đúng
- Kiểm tra tích hợp giữa các tầng
- Đảm bảo thông tin được truyền chính xác giữa các tầng
- Xác minh rằng Relationship Services được tích hợp đúng cách
- Phát hiện và sửa lỗi nếu có

## 1. Kiểm tra từng thành phần riêng biệt

### 1.1 Working Memory Service
**Mục tiêu:** Kiểm tra rằng Working Memory Service hoạt động đúng

**Các bước kiểm tra:**
- [ ] Tạo instance của `WorkingMemoryService`
- [ ] Thêm tin nhắn vào working memory với `add_message()`
- [ ] Kiểm tra mức độ quan trọng được đánh giá đúng
- [ ] Kiểm tra category được phân loại đúng
- [ ] Kiểm tra `get_context()` trả về đúng thông tin
- [ ] Kiểm tra `get_recent_conversation()` hoạt động đúng
- [ ] Kiểm tra `search_by_category()` và `search_by_keywords()` hoạt động đúng
- [ ] Kiểm tra trigger threshold hoạt động đúng

**Công cụ kiểm tra:**
- Sử dụng `debug_working_memory()` từ `debug_utils.py`
- Thêm logging chi tiết để theo dõi hoạt động

### 1.2 Episodic Memory Service
**Mục tiêu:** Kiểm tra rằng Episodic Memory Service hoạt động đúng

**Các bước kiểm tra:**
- [ ] Kiểm tra `MemoryBackgroundService._update_episodic_memory()` hoạt động đúng
- [ ] Kiểm tra việc trích xuất facts/events từ hội thoại
- [ ] Kiểm tra việc lưu trữ vào file `user_id_episodic.json`
- [ ] Kiểm tra việc dọn dẹp working memory sau khi trích xuất
- [ ] Kiểm tra `get_episodic_memory()` trả về đúng thông tin

**Công cụ kiểm tra:**
- Sử dụng `debug_episodic_memory()` từ `debug_utils.py`
- Kiểm tra trực tiếp file `user_id_episodic.json`

### 1.3 Core Persona Service
**Mục tiêu:** Kiểm tra rằng Core Persona Service hoạt động đúng

**Các bước kiểm tra:**
- [ ] Kiểm tra `MemoryBackgroundService._update_core_persona()` hoạt động đúng
- [ ] Kiểm tra việc tổng hợp thông tin từ episodic memory
- [ ] Kiểm tra việc lưu trữ vào file `user_id_summary.txt`
- [ ] Kiểm tra `get_core_persona()` trả về đúng thông tin
- [ ] Kiểm tra việc cập nhật thông tin mới và giữ lại thông tin cũ

**Công cụ kiểm tra:**
- Sử dụng `debug_core_persona()` từ `debug_utils.py`
- Kiểm tra trực tiếp file `user_id_summary.txt`

### 1.4 Relationship Service
**Mục tiêu:** Kiểm tra rằng Relationship Service hoạt động đúng

**Các bước kiểm tra:**
- [ ] Kiểm tra `process_message()` xử lý đúng thông tin mối quan hệ
- [ ] Kiểm tra `get_user_relationships()` trả về đúng thông tin
- [ ] Kiểm tra `get_interaction_stats()` hoạt động đúng
- [ ] Kiểm tra việc trích xuất thông tin mối quan hệ từ LLM
- [ ] Kiểm tra việc lưu trữ vào file `relationships.json`

**Công cụ kiểm tra:**
- Sử dụng `debug_relationships()` từ `debug_utils.py`
- Kiểm tra trực tiếp các file trong thư mục `relationships/`

## 2. Kiểm tra tích hợp giữa các tầng

### 2.1 Working Memory ↔ Episodic Memory
**Mục tiêu:** Kiểm tra việc chuyển thông tin từ Working Memory sang Episodic Memory

**Các bước kiểm tra:**
- [ ] Gửi 20 tin nhắn để kích hoạt trigger
- [ ] Kiểm tra rằng `_update_episodic_memory()` được gọi
- [ ] Kiểm tra rằng facts được trích xuất đúng
- [ ] Kiểm tra rằng working memory được dọn dẹp sau khi trích xuất
- [ ] Kiểm tra rằng thông tin được lưu đúng vào episodic memory

**Công cụ kiểm tra:**
- Sử dụng `debug_triggers()` để kiểm tra trạng thái trigger
- Theo dõi log để xác nhận các hàm được gọi

### 2.2 Episodic Memory ↔ Core Persona
**Mục tiêu:** Kiểm tra việc cập nhật Core Persona từ Episodic Memory

**Các bước kiểm tra:**
- [ ] Tạo hơn 50 sự kiện trong episodic memory
- [ ] Kiểm tra rằng `_update_core_persona()` được gọi
- [ ] Kiểm tra rằng thông tin mới được tích hợp vào core persona
- [ ] Kiểm tra rằng thông tin cũ vẫn được giữ lại nếu còn chính xác

**Công cụ kiểm tra:**
- Theo dõi log để xác nhận các hàm được gọi
- So sánh nội dung trước và sau khi cập nhật

### 2.3 Relationship Service ↔ Core Persona
**Mục tiêu:** Kiểm tra việc tích hợp thông tin mối quan hệ vào Core Persona

**Các bước kiểm tra:**
- [ ] Gửi tin nhắn có chứa thông tin mối quan hệ
- [ ] Kiểm tra rằng thông tin được nhận diện đúng
- [ ] Kiểm tra rằng thông tin mối quan hệ được đưa vào prompt cập nhật core persona
- [ ] Kiểm tra rằng core persona được cập nhật với thông tin mối quan hệ mới

**Công cụ kiểm tra:**
- Sử dụng `debug_relationships()` và `debug_core_persona()`
- Kiểm tra nội dung prompt được gửi đến LLM

## 3. Kiểm tra cơ chế trigger và background service

### 3.1 Activity Monitor
**Mục tiêu:** Kiểm tra rằng Activity Monitor hoạt động đúng

**Các bước kiểm tra:**
- [ ] Kiểm tra `record_activity()` ghi nhận hoạt động đúng
- [ ] Kiểm tra `_check_all_conditions()` kiểm tra điều kiện đúng
- [ ] Kiểm tra `_trigger_message_count()` và `_trigger_timeout()` hoạt động đúng
- [ ] Kiểm tra callback được gọi đúng khi trigger

**Công cụ kiểm tra:**
- Thêm logging để theo dõi các trigger
- Kiểm tra `get_user_status()` trả về đúng trạng thái

### 3.2 Background Service
**Mục tiêu:** Kiểm tra rằng MemoryBackgroundService hoạt động đúng

**Các bước kiểm tra:**
- [ ] Kiểm tra `_background_worker()` chạy đúng
- [ ] Kiểm tra `_check_and_update_core_personas()` hoạt động đúng
- [ ] Kiểm tra `start()` và `stop()` hoạt động đúng
- [ ] Kiểm tra rằng background service không ảnh hưởng đến luồng chính

**Công cụ kiểm tra:**
- Theo dõi log của background service
- Kiểm tra hiệu suất hệ thống khi background service chạy

## 4. Kiểm tra tích hợp hoàn chỉnh

### 4.1 MemoryManager
**Mục tiêu:** Kiểm tra rằng MemoryManager tích hợp tất cả các tầng đúng

**Các bước kiểm tra:**
- [ ] Kiểm tra `add_message()` hoạt động đúng
- [ ] Kiểm tra `get_context()` trả về thông tin từ cả 3 tầng
- [ ] Kiểm tra `get_working_memory_context()`, `get_core_persona()`, `get_episodic_memory()` hoạt động đúng
- [ ] Kiểm tra `trigger_episodic_update()` và `trigger_persona_update()` hoạt động đúng
- [ ] Kiểm tra `get_memory_status()` trả về đúng trạng thái

**Công cụ kiểm tra:**
- Sử dụng `debug_memory_status()` từ `debug_utils.py`
- Kiểm tra toàn bộ hệ thống với `get_all_debug_info()`

### 4.2 LLMMessageCog
**Mục tiêu:** Kiểm tra rằng LLMMessageCog sử dụng MemoryManager đúng

**Các bước kiểm tra:**
- [ ] Kiểm tra `_process_ai_response_with_memory()` sử dụng context từ MemoryManager
- [ ] Kiểm tra `_build_enhanced_context_with_memory()` xây dựng context đúng
- [ ] Kiểm tra rằng thông tin từ cả 3 tầng được đưa vào context cho LLM
- [ ] Kiểm tra rằng tin nhắn được thêm vào MemoryManager đúng

**Công cụ kiểm tra:**
- Sử dụng các lệnh debug trong bot: `!debug_memory_status`, `!debug_all`, v.v.
- Theo dõi log để xác nhận các hàm được gọi

## 5. Kịch bản thử nghiệm cụ thể

### 5.1 Kịch bản 1: Gửi tin nhắn thông thường
**Mục tiêu:** Kiểm tra luồng cơ bản

**Các bước:**
1. Gửi tin nhắn "Xin chào, mình tên là John"
2. Kiểm tra rằng tin nhắn được thêm vào Working Memory
3. Kiểm tra rằng context được xây dựng đúng
4. Kiểm tra rằng phản hồi được tạo và gửi đúng

**Kỳ vọng:**
- Tin nhắn được lưu vào Working Memory với mức độ quan trọng cao
- Thông tin tên được nhận diện và có thể được lưu vào Core Persona sau này

### 5.2 Kịch bản 2: Gửi nhiều tin nhắn để kích hoạt trigger
**Mục tiêu:** Kiểm tra cơ chế trigger

**Các bước:**
1. Gửi 20 tin nhắn liên tiếp
2. Kiểm tra rằng trigger được kích hoạt
3. Kiểm tra rằng Episodic Memory được cập nhật
4. Kiểm tra rằng Working Memory được dọn dẹp

**Kỳ vọng:**
- Sau tin nhắn thứ 20, trigger được kích hoạt
- Facts được trích xuất và lưu vào Episodic Memory
- Một số tin nhắn cũ được xóa khỏi Working Memory

### 5.3 Kịch bản 3: Gửi tin nhắn có thông tin mối quan hệ
**Mục tiêu:** Kiểm tra tích hợp Relationship Service

**Các bước:**
1. Gửi tin nhắn "Bạn mình tên là Anna, mình rất quý Anna"
2. Kiểm tra rằng thông tin mối quan hệ được nhận diện
3. Kiểm tra rằng thông tin được lưu vào Relationship Service
4. Kiểm tra rằng thông tin được đưa vào Core Persona sau khi cập nhật

**Kỳ vọng:**
- Thông tin mối quan hệ được nhận diện và lưu trữ
- Mối quan hệ với Anna được ghi nhận
- Thông tin được tích hợp vào hồ sơ người dùng

### 5.4 Kịch bản 4: Kiểm tra inactivity timeout
**Mục tiêu:** Kiểm tra cơ chế timeout

**Các bước:**
1. Gửi một vài tin nhắn
2. Chờ hơn 10 phút không hoạt động
3. Kiểm tra rằng timeout trigger được kích hoạt
4. Kiểm tra rằng Episodic Memory được cập nhật

**Kỳ vọng:**
- Sau 10 phút không hoạt động, trigger được kích hoạt
- Thông tin từ phiên hội thoại được trích xuất vào Episodic Memory

## 6. Công cụ debug và logging

### 6.1 Debug Utils
**Mục tiêu:** Sử dụng các công cụ debug đã tạo

**Các công cụ:**
- `debug_memory_status()` - Kiểm tra trạng thái tổng thể
- `debug_working_memory()` - Kiểm tra working memory
- `debug_episodic_memory()` - Kiểm tra episodic memory
- `debug_core_persona()` - Kiểm tra core persona
- `debug_relationships()` - Kiểm tra relationship
- `debug_triggers()` - Kiểm tra trigger
- `get_all_debug_info()` - Lấy toàn bộ thông tin debug

### 6.2 Logging
**Mục tiêu:** Theo dõi hoạt động của hệ thống

**Các mức log cần theo dõi:**
- INFO: Các hoạt động chính như thêm tin nhắn, cập nhật bộ nhớ
- DEBUG: Chi tiết về quá trình xử lý, đánh giá mức độ quan trọng
- WARNING: Các vấn đề tiềm ẩn
- ERROR: Các lỗi xảy ra

## 7. Xác minh cuối cùng

### 7.1 Kiểm tra hiệu suất
- [ ] Đo thời gian phản hồi của bot
- [ ] Kiểm tra việc sử dụng bộ nhớ
- [ ] Kiểm tra ảnh hưởng của background service đến luồng chính

### 7.2 Kiểm tra tính chính xác
- [ ] Xác minh rằng thông tin được lưu trữ chính xác
- [ ] Kiểm tra rằng thông tin không bị mất khi chuyển giữa các tầng
- [ ] Xác minh rằng Core Persona được cập nhật đúng cách

### 7.3 Kiểm tra tính ổn định
- [ ] Chạy thử nghiệm dài hạn
- [ ] Kiểm tra xử lý lỗi và phục hồi
- [ ] Xác minh rằng hệ thống không bị treo hoặc crash

## 8. Báo cáo kết quả
- [ ] Ghi lại tất cả các lỗi phát hiện
- [ ] Ghi lại các cải tiến cần thiết
- [ ] Tạo tài liệu hướng dẫn debug cho các nhà phát triển khác
