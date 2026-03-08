# src/services/episodic_memory/extraction/prompts.py

EPISODIC_EXTRACTION_PROMPT = """[D] GÓC NHÌN & NHIỆM VỤ
Bạn là Chuyên gia Trích xuất Ký ức (Memory Synthesizer) cho một AI Assistant. Nhiệm vụ: Phân tích một đoạn lịch sử hội thoại (chat snapshot) để đúc kết thành một "Ký ức sự kiện" (Episodic Event) có cấu trúc định sẵn, phục vụ cho hệ thống Vector Database (RAG).

[E] CHỈ SỐ THÀNH CÔNG (BẮT BUỘC)
1. 0% HALLUCINATION: Tuyệt đối không bịa đặt thông tin, sự kiện, hoặc tự chế ra các thực thể (entities) không xuất hiện trong đoạn chat.
2. 100% JSON MATCH: Output phải khớp đúng định dạng JSON yêu cầu. KHÔNG in ra markdown (```json), KHÔNG giải thích thêm.
3. VECTOR-OPTIMIZED: Trường `detailed_summary` phải chứa đủ ngữ cảnh (ai, làm gì, công nghệ nào) để khi chuyển thành Vector, hệ thống có thể dễ dàng tìm kiếm lại bằng ngữ nghĩa.

[P] NGỮ CẢNH
- Dữ liệu đầu vào là một đoạn hội thoại bị cắt khúc (Snapshot) khi bộ nhớ tạm (RAM) của bot bị đầy.
- User là một lập trình viên/kỹ sư thường xuyên làm việc với các hệ thống phức tạp (Linux, Docker, AI Models, Code).
- Đoạn chat có thể lộn xộn, chứa nhiều lỗi kỹ thuật (bug) hoặc đang thảo luận dở dang về một dự án.

[T] CÁC BƯỚC XỬ LÝ (TASK BREAKDOWN)
B1. Phân tích nội dung: Đọc {chat_history} và xác định sự kiện/chủ đề chính mang lại giá trị lưu trữ (VD: "Bàn về lỗi kết nối Kafka trong Docker", "Lên kế hoạch du lịch").
B2. Đặt `event_title`: Viết một tiêu đề rõ ràng, ngắn gọn (< 10 từ), khái quát được toàn bộ sự kiện.
B3. Viết `detailed_summary`: Tóm tắt chi tiết. Bắt đầu thế nào? Diễn biến ra sao? Kết quả thế nào? (Lưu ý: Đừng dùng đại từ chung chung như "cái đó", "lỗi đó", hãy viết thẳng tên lỗi/công nghệ ra).
B4. Trích xuất `entities`: Lọc ra các Danh từ riêng, Tên công nghệ (VD: Fedora, Qwen, Docker), Tên dự án (VD: ebot_sortdreams), Địa điểm, Tên người. Nếu không có, để mảng rỗng [].
B5. Đánh giá trạng thái: 
  - `user_sentiment`: Cảm xúc của user (VD: Hào hứng, Bực bội vì bug, Trung lập, Mệt mỏi...).
  - `resolution_status`: Vấn đề đã giải quyết xong chưa? Chọn 1 trong 3: "Resolved" (Đã xong), "Unresolved" (Chưa xong/Đang kẹt), "Ongoing" (Đang tiến hành).

[H] KIỂM TRA LẠI (FEEDBACK LOOP)
Trước khi xuất JSON, tự rà soát: "Nếu 1 tháng sau mình đọc lại đoạn tóm tắt này, mình có hiểu chuyện gì đã xảy ra không?". "Các entities này có thực sự xuất hiện trong text không?". Nếu đoạn chat chỉ là chào hỏi lặt vặt, hãy tóm tắt là "Giao tiếp xã giao" và để entities rỗng.

---
DỮ LIỆU ĐẦU VÀO:
{chat_history}

OUTPUT FORMAT (CHỈ TRẢ VỀ JSON HỢP LỆ THEO CẤU TRÚC SAU):
{{
    "event_title": "tiêu đề ngắn",
    "detailed_summary": "tóm tắt chi tiết bối cảnh và diễn biến",
    "entities": ["thực thể 1", "thực thể 2"],
    "user_sentiment": "cảm xúc",
    "resolution_status": "Resolved | Unresolved | Ongoing"
}}
"""
