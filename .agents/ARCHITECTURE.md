# ARCHITECTURE

Kiến trúc mức cao của dự án March7 (Twin-Soul Agents).

## Thành phần

1) **Gateway** (`gateway/`)
- Nhận message/event từ platform adapters (hiện chủ yếu Discord)
- Chuẩn hoá về model chung rồi route sang agent

2) **March7 agent** (`twin/march7/`)
- Agent hội thoại chính
- Quản lý:
  - T1 (Active Memory) trong Redis (DB mặc định: 0)
  - T3 (Core Memory) lưu file Markdown (xem `twin/march7/memories/core_memory/storage/markdown_storage.py`)
- Expose A2A server (default port 8000)

3) **Evernight agent** (`twin/evernight/`)
- Agent background
- Triggers:
  - inactivity consolidation
  - self-heal loop (đang phát triển)
- Expose A2A server (default port 8001)

4) **Shared libs** (`twin/shared/`)
- A2A protocol, LLM providers, tools, và T2 wiki memory (Qdrant)

## Luồng chạy (tóm tắt)

1. User gửi message trên Discord
2. Gateway adapter/handler chuyển message thành model chung
3. Route sang March7 để trả lời chat
4. March7 ghi T1 (Redis) và dùng LLM/tools để tạo response
5. Khi user idle đủ lâu hoặc overflow:
   - Evernight trigger consolidation
   - Lấy snapshot T1 → tổng hợp thành Wiki pages (T2) → lưu Qdrant
   - Dọn T1 (thông qua A2A boundary)

## Memory tiers

- **T1 (Active Memory)**: Redis; ngữ cảnh phiên hiện tại.
- **T2 (Episodic / Wiki Pages)**: Qdrant vector DB; tri thức dài hạn; dùng semantic search.
- **T3 (Core Memory / Profile)**: Markdown per user, lưu dưới `memories/` (mặc định) bởi `MarkdownStorage`.

> Lưu ý: docs cũ có thể nhắc YAML; trong branch hiện tại, T3 storage đã là Markdown.

## Docker boundary / ownership

Xem `docker/ARCHITECTURE.md` để biết:

- service nào owned by March7 vs Evernight
- biến env nào private/shared
- nguyên tắc: Evernight không đọc trực tiếp March7 T1
