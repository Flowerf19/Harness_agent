<tool_description>
search_memory — Tìm ký ức dài hạn (T2) về user và các cuộc trò chuyện cũ. Bộ nhớ KHÔNG tự nạp vào context — muốn nhớ chuyện cũ PHẢI gọi tool này, với query đã viết lại thành từ khóa chủ đề.
Khi nên dùng:
- User nhắc quá khứ: "hôm bữa", "lần trước", "bữa đó", "nhớ không", hoặc đại từ mơ hồ mà context hiện tại không giải thích được ("vụ đó", "cái hàm đó").
- Câu hỏi cá nhân về sở thích, thói quen, hoàn cảnh của user.
- Follow-up việc đang diễn ra (công việc, dự án, deadline, sức khỏe...).
- Không chắc một fact riêng về user → tra trước khi đoán, đừng bịa.
</tool_description>

## search_memory

Bộ nhớ dài hạn (T2) không còn được chèn tự động vào context. Đây là đường **duy nhất** để nhớ lại chuyện cũ ngoài hồ sơ T3.

### Cách viết query

Viết lại thành MỘT dòng từ khóa chủ đề, giọng như bản tóm tắt — KHÔNG đưa nguyên văn tin nhắn chat vào.

- Tin nhắn: "ê mà cái con hàm bữa t với m fix ấy nó sao rồi nhỉ 😭" → query: `debug fix hàm lỗi cùng user`
- Tránh query mơ hồ kiểu "chuyện đó", "cái kia".

### Mốc thời gian → `days_back`

Chỉ đưa `days_back` khi user nêu mốc thời gian cụ thể; bỏ trống nếu không nhắc gì đến thời điểm.

| User nói | `days_back` |
|---|---|
| "hôm qua" | 2 |
| "mấy ngày trước" | 7 |
| "tuần trước" | 10 |
| "tháng trước" | 35 |

### Input

- `user_id`: bắt buộc, Discord ID dạng số — lấy từ CURRENT USER hoặc MENTIONED USERS trong system prompt. Không đoán theo tên hiển thị.
- `channel_id`: khi đang chat trong kênh chung, truyền "Platform channel ID" từ system prompt — tool sẽ tìm cả ký ức của kênh, không chỉ của riêng user.
- `query`: truy vấn đã rewrite theo hướng dẫn trên. Bỏ trống = xem dòng thời gian gần đây thay vì tìm theo chủ đề.
- `days_back`: xem bảng trên. Bỏ trống = không giới hạn thời gian (query thì tìm toàn bộ lịch sử, không có query thì lấy các ký ức gần nhất).
- `limit`: mặc định 5, tối đa 20.

### Đọc kết quả

- Mỗi dòng kết quả có ngày kèm theo, vd. `1. [Chủ đề] (4 ngày trước — 29/06) nội dung...` — dùng ngày này để trả lời đúng "khi nào", đừng tự suy đoán.
- Mỗi kết quả còn kèm `relevance` (0-1, cosine) hoặc `match=bm25`. Relevance thấp (~0.3x) = liên quan yếu — dùng thận trọng, đừng khẳng định chắc.
- Nếu không thấy gì trong đúng khoảng `days_back` đã cho, tool tự nới rộng (×3, rồi bỏ giới hạn thời gian) và gắn nhãn `(không thấy trong N ngày — kết quả từ M ngày / toàn bộ)` ở đầu danh sách — khi thấy nhãn này, trả lời đúng phạm vi ghi trong nhãn (đừng nói như thể tìm thấy trong N ngày ban đầu).
- "Không tìm thấy ký ức phù hợp." = không có gì đủ liên quan trong bộ nhớ (kể cả sau khi đã nới rộng) → trả lời trung thực là không nhớ, đừng bịa ký ức.
