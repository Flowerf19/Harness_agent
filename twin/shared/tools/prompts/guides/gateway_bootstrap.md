<tool_description>
gateway_bootstrap — Quy trình ngắn để hướng dẫn owner cài System Gateway khi GatewayMonitor báo MISSING hoặc `gateway_admin doctor` trả `missing`.
</tool_description>

## gateway_bootstrap

System Gateway là service native trên host. Khi gateway chưa phản hồi, agent
không tự cài được; agent chỉ đưa owner lệnh bootstrap trong repo March7.

### Quy tắc

- Luôn gọi `gateway_admin doctor` trước để biết trạng thái thật.
- Nếu gateway `healthy`/`degraded`, báo trạng thái đó; không hướng dẫn cài lại.
- Nếu gateway `missing`, dùng `gateway_admin install` hoặc `install_hint`.
- Nếu owner đã đưa thư mục cài March7 hoặc path tới `scripts/bootstrap_system_gateway.py`,
  truyền path đó vào `install_path`. Tool tự cắt về project root và tự biết phần
  còn lại của kiến trúc project (`scripts/bootstrap_system_gateway.py`,
  `services/system_gateway/`).
- Nếu chưa có path, hỏi đúng thư mục cài March7 trên host. Không bảo owner chạy
  `find /...` trừ khi owner chủ động hỏi cách tự tìm.
- Lệnh gửi owner phải là code block từ tool. Không tự ghép `pip`, `curl`,
  `systemctl`, hay path khác.

### Câu trả lời mong muốn

Khi đã có path:

```text
Chạy trên host:
<code block từ gateway_admin install install_path=...>
```

Khi chưa có path:

```text
Gateway đang tắt. Gửi thư mục cài March7 trên host, rồi mình đưa đúng lệnh chạy.
Nếu biết path file bootstrap cũng được: .../scripts/bootstrap_system_gateway.py
```

Sau khi owner báo chạy xong, gọi lại `gateway_admin doctor` và báo kết quả ngắn.
