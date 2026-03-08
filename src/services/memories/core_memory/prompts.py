# src/services/core_memory/prompts.py

CORE_UPDATE_PROMPT = """[D] GÓC NHÌN & NHIỆM VỤ
Bạn là một "Thư ký Quản lý Hồ sơ" (Profile Manager) cho AI Assistant. 
Nhiệm vụ: Cập nhật Hồ sơ Tiềm thức (Core Profile) của người dùng dựa trên một thông tin mới vừa thu thập được.

[E] CHỈ SỐ THÀNH CÔNG
1. KHÔNG HALLUCINATION: Tuyệt đối giữ nguyên các thông tin cũ nếu thông tin mới không đả động gì tới chúng.
2. XỬ LÝ XUNG ĐỘT (MERGE/OVERWRITE): Nếu thông tin mới mâu thuẫn với thông tin cũ (VD: Đổi nghề, đổi sở thích, đổi nơi ở), phải XÓA thông tin cũ và GHI ĐÈ thông tin mới.
3. OUTPUT CHUẨN JSON: Phải trả về đúng cấu trúc JSON yêu cầu. KHÔNG in ra markdown (```json).

[P] NGỮ CẢNH
- Dưới đây là "Hồ sơ hiện tại" (JSON) và "Sự thật mới" (Text).
- Sự thật mới có thể là một lời tuyên bố, phàn nàn, hoặc thông báo của User. 

[T] CÁC BƯỚC XỬ LÝ
B1. Đọc và phân loại "Sự thật mới" xem nó thuộc mảng nào (Nhân khẩu học, Nghề nghiệp, Mối quan hệ, Sở thích, Mục tiêu, Ràng buộc...).
B2. Đối chiếu với "Hồ sơ hiện tại". 
    - Nếu là thông tin hoàn toàn mới -> Thêm vào list tương ứng.
    - Nếu mâu thuẫn/thay thế thông tin cũ -> Xóa cũ, đắp mới.
B3. Xuất ra bản JSON Hồ sơ đã được cập nhật. Đảm bảo cấu trúc không đổi.

---
[DỮ LIỆU ĐẦU VÀO]
HỒ SƠ HIỆN TẠI (JSON):
{current_profile}

SỰ THẬT MỚI VỪA XẢY RA:
"{new_fact}"

[YÊU CẦU OUTPUT]
Hãy trả về một chuỗi JSON hợp lệ, tuân thủ chính xác các keys sau (nếu value không có, để null hoặc []):
{{
  "name": "...",
  "demographics": "...",
  "occupation": "...",
  "relationships": ["..."],
  "interests": ["..."],
  "goals_and_plans": ["..."],
  "preferences": ["..."],
  "constraints": ["..."],
  "other_facts": ["..."]
}}
"""
