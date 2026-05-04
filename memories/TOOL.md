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
* **Parameters:**
    - `query` (required): Từ khóa tìm kiếm. LUÔN đính kèm năm hiện tại (`2026`) hoặc `"mới nhất"`, `"hôm nay"` để tránh data cũ.
    - `search_depth`: `"basic"` (nhanh, tiết kiệm) hoặc `"advanced"` (deep research, tốn hơn). Dùng `"advanced"` khi query cần phân tích sâu, so sánh nhiều nguồn.
    - `max_results` (1-10): Số kết quả trả về. Default 5. Tăng khi cần khảo sát rộng, giảm khi query cụ thể.
    - `topic`: `"general"` (mặc định) hoặc `"news"` (tin tức thời sự, sự kiện nóng). Dùng `"news"` khi user hỏi về tin mới, trending, breaking news.
    - `time_range`: `"day"`, `"week"`, `"month"`, `"year"`. Giới hạn kết quả theo khoảng thời gian. VD: user hỏi "tin AI tuần này" → `time_range="week"`.
    - `include_domains`: List domain whitelist. Dùng khi user yêu cầu nguồn cụ thể hoặc cần nguồn uy tín (VD: `["wikipedia.org", "britannica.com"]`).
    - `exclude_domains`: List domain blacklist. Loại trừ nguồn kém uy tín.
* **Quy tắc:**
    - Tuyệt đối không dùng để tìm lịch sử user (dùng `search_memory`).
    - Ưu tiên `topic="news"` + `time_range="week"` cho câu hỏi về sự kiện hiện tại.
    - Dùng `include_domains` khi cần độ chính xác cao (scientific, academic).
    - Query bằng tiếng Việt hoặc tiếng Anh tùy context — Tavily hỗ trợ đa ngôn ngữ.

### 🐍 `run_python_code` (Data & Logic Sandbox)
* **Chức năng:** Tính toán phức tạp, phân tích/biến đổi dữ liệu (CSV, JSON), chạy script mô phỏng, shell commands.
* **Parameters:**
    - `user_id` (required): Discord user ID. Biến/state lưu riêng per-user.
    - `code` (required): Mã Python hoặc shell command cần thực thi. KHÔNG bao gồm markdown ticks.
    - `kernel`: `"ipython"` (mặc định — chạy Python code) hoặc `"bash"` (chạy shell commands như `ls`, `curl`, `pip install`, `cat`, v.v.).
    - `cwd`: Thư mục làm việc. Mặc định là `/.codebox/` (internal sandbox path). Có thể set `/workspace` để đổi thư mục.
    - `file_content`: Nội dung file cần upload (base64 encoded). Gửi kèm `filename` để upload file vào sandbox trước khi exec.
    - `filename`: Tên file khi upload (VD: `"data.csv"`, `"chart.png"`). Required nếu có `file_content`.
    - `download_file_name`: Tên file cần tải từ sandbox. Nếu có, tool trả về nội dung file (base64) thay vì exec code.
* **Quy tắc:**
    * **Stateful**: Biến/functions persist xuyên suốt session của user. VD: `x = 5` ở call 1 → `print(x * 2)` ở call 2 → ra `10`.
    * **Kernel selection**:
        - Dùng `"ipython"` cho: tính toán, phân tích data, matplotlib, numpy, pandas.
        - Dùng `"bash"` cho: xem file (`ls`, `cat`), cài package (`pip install`), system info (`uname`, `df`).
    * **File workflow**:
        - Upload: Encode file → base64 → gửi `file_content` + `filename` → file lưu tại `/.codebox/{filename}` (default working dir).
        - Download: Gửi `download_file_name` → trả về base64 content của file trong sandbox.
        - Upload rồi phân tích: Upload CSV → exec code đọc file → download result.
    * **Working directory**:
        - Default: `/.codebox/` — đây là nơi kernel chạy và file được lưu/upload.
        - Có thể dùng `cwd="/workspace"` để đổi working dir (VD: bash commands cần access system paths).
        - Khi đọc file vừa upload: dùng path `/.codebox/{filename}` hoặc chỉ `{filename}` (nếu không đổi cwd).
    * **Cho phép**: `!pip install`, import thư viện có sẵn (numpy, pandas, matplotlib, requests trong sandbox).
    * **Cấm**: Dùng code để tự gọi API bên ngoài (phải dùng `web_search`), access file hệ thống ngoài `/workspace`.
* **Examples:**
    - Python calc: `kernel="ipython"`, `code="import math\nprint(math.sqrt(144))"`
    - Bash list files: `kernel="bash"`, `code="ls -la /workspace/"`
    - Upload CSV + analyze: `file_content=<base64>`, `filename="data.csv"`, `code="import pandas as pd\ndf = pd.read_csv('/workspace/data.csv')\nprint(df.describe())"`
    - Download chart: Upload + exec code generate matplotlib chart → `download_file_name="chart.png"`

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
| Dùng `run_python_code` để `requests.get()` gọi API | Dùng `web_search` — sandbox không có internet access |
| `run_python_code(code="import os; os.listdir('/')")` | Dùng `kernel="bash"`, `code="ls /workspace/"` — chỉ access `/workspace/` |
| Hard-code absolute path ngoài `/workspace/` | Dùng `/workspace/` — đây là working directory mặc định |