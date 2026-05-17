# AGENT_RULES

Quy tắc khi agent làm việc trong repo này.

## 1) Security / Safety (bắt buộc)

1. **Không tiết lộ secrets**
   - Không in ra nội dung `.env`, token Discord, API keys, URLs có credentials.
   - Không commit secrets. Nếu thấy secrets trong repo, dừng và báo ngay.

2. **Bash Executor là “privileged tool”**
   - Chỉ dùng khi thật cần thiết.
   - Mọi lệnh phải được user approve (theo thiết kế tool).
   - Tránh lệnh destructive (`rm -rf`, `shutdown`, `mkfs`, `dd`, thay đổi firewall…) trừ khi user yêu cầu rõ.
   - Tham chiếu: [README_BASH_EXECUTOR.md](../README_BASH_EXECUTOR.md).

3. **Boundary March7 ↔ Evernight (A2A)**
   - Evernight **không đọc trực tiếp** Redis keys của March7 T1 nếu không được thiết kế cho coordination.
   - Tương tác với March7 memory thông qua A2A (`get_snapshot`, `clear_session`, …) theo mô tả trong [docker/ARCHITECTURE.md](../docker/ARCHITECTURE.md).

## 2) Reliability / Quality

- Khi sửa code liên quan external I/O (Discord/HTTP/Redis/Qdrant/LLM):
  - Thêm/giữ **timeout** hợp lý
  - Thêm **retry/backoff** nếu phù hợp
  - Log đủ để debug nhưng **không log secrets**

## 3) Repo hygiene

- Thay đổi kiến trúc/flow: cập nhật docs tương ứng trong `.github/`.
- Thay đổi schema/key của memory: update tests + update `GLOSSARY.md`/`MEMORY.md`.
