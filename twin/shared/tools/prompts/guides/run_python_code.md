<tool_description>
Chạy Python hoặc bash trong sandbox CodeBox/Jupyter. Trạng thái được giữ riêng theo từng user.


## run_python_code

Chạy Python hoặc bash trong sandbox CodeBox/Jupyter. Trạng thái được giữ riêng theo từng user.

### Khi nên dùng

- Tính toán cần chính xác, phân tích dữ liệu, tạo/kiểm tra script, đọc/xử lý file trong sandbox.
- Cần pandas/numpy/matplotlib hoặc cần chạy đoạn code ngắn để kiểm chứng.

### Khi không nên dùng

- Thông tin web/current: dùng `web_search`.
- Trạng thái máy host, docker, log: dùng `host_system`.
- Câu hỏi đơn giản có thể trả lờitrực trực tiếp.
</tool_description>

### Input

- `user_id`: Discord ID dạng số để có session riêng.
- `code`: code dạng plain text, không bọc markdown fence.
- `kernel`: `ipython` mặc định; `bash` cho pip/list/file ops trong sandbox.
- `cwd`: mặc định `/workspace`.
- `file_content` + `filename`: upload file base64.
- `download_file_name`: lấy file output dạng base64.

### Lỗi cần tránh

- Không dùng `requests.get()` để thay `web_search`.
- Không dùng cho lệnh host thật.
- Nếu cần nhiều bước, có thể gọi tiếp vì session giữ biến.
