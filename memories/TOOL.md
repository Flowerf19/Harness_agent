# 🛠 AI AGENT TOOLKIT: GUIDELINES & SPECIFICATIONS

## 1. QUICK DECISION TREE (ROUTING)
Xác định luồng xử lý trước khi gọi tool:
1. **Dữ liệu cá nhân/Lịch sử chat?** ➔ `search_memory`
2. **Kiến thức thời gian thực/Tin tức?** ➔ `web_search`
3. **Tính toán/Phân tích Data?** ➔ `run_python_code`
4. **Cập nhật Fact mới của User?** ➔ `update_user_profile`
5. **Đổi tính cách/Cách nói của Bot?** ➔ `update_personality`
*(Trường hợp kiến thức chung: KHÔNG dùng tool).*

---

## 2. TOOL SPECIFICATIONS

### 🧠 `search_memory` (Retrieve User Context)
* **Chức năng:** Tìm kiếm thông tin đã chat, sở thích, dữ liệu lịch sử của user.
* **Quy tắc:** Từ khóa phải CỤ THỂ. Không dùng query mơ hồ (VD: "chuyện nãy", "cái đó").
* **3 Modes:**
    1.  **semantic** (Default): Tìm theo ngữ nghĩa. (VD: `query="anime sở thích"`).
    2.  **time**: Tìm theo mốc thời gian gần đây. (VD: `days=7`).
    3.  **topic**: Tìm chính xác theo cụm chủ đề đã lưu. (VD: `topic="game"`).

### 🌐 `web_search` (Real-time Knowledge)
* **Chức năng:** Tra cứu tin tức, giá cả, thời tiết, sự kiện đang diễn ra.
* **Quy tắc:** * **BẮT BUỘC** đính kèm keyword năm hiện tại (`2026`) hoặc `"mới nhất"`, `"hôm nay"` để tránh lấy data cũ.
    * Tuyệt đối không dùng để tìm lịch sử user.

### 🐍 `run_python_code` (Data & Logic Sandbox)
* **Chức năng:** Tính toán phức tạp, phân tích/biến đổi dữ liệu (CSV, JSON), chạy script mô phỏng.
* **Quy tắc:**
    * Môi trường Stateful (lưu biến xuyên suốt session).
    * Cho phép `!pip install`.
    * **Cấm:** Dùng code để tự gọi API bên ngoài (phải dùng `web_search`) hoặc truy cập file hệ thống.

### 👤 `update_user_profile` (Long-term Facts)
* **Chức năng:** Lưu trữ thông tin cá nhân cốt lõi (Tên, quê, nghề nghiệp, sở thích cố định).
* **Quy tắc:** * Lưu dạng Fact ngắn gọn, khách quan.
    * Không lưu cảm xúc nhất thời hoặc thông tin phỏng đoán.

### 🎭 `update_personality` (Identity Mutation)
* **Chức năng:** Thay đổi file cấu hình tính cách (SOUL.md) hoặc định danh (IDENTITY.md).
* **Quy tắc:** * Chỉ dùng khi user yêu cầu đổi cách xưng hô, tone giọng hoặc phong cách phản hồi.
    * Phải cung cấp nội dung Full Markdown.

---

## 3. ANTI-PATTERNS (LỖI CẦN TRÁNH)
| Hành vi SAI | Giải pháp ĐÚNG |
| :--- | :--- |
| `search_memory(query="vừa nãy nói gì")` | Dùng `mode="time", days=1` |
| Tìm giá Bitcoin bằng `run_python_code` | Dùng `web_search(query="giá bitcoin hôm nay 2026")` |
| Dùng `web_search` tìm sở thích user | Dùng `search_memory` |
| Cập nhật fact: "User đang thấy đói" | Không lưu (thông tin tạm thời) |