# Bé Bảy (March7) — Twin-Soul AI Assistant for Discord

Bé Bảy là hệ Twin-Soul AI trên Discord: `march7` là agent hội thoại chính, còn `evernight` là agent độc lập vừa trò chuyện qua DM/tag/prefix vừa làm background consolidation, notification và self-heal. Hai agent giao tiếp qua A2A.

## Tính năng chính

- **Discord AI assistant**: hội thoại tự nhiên + tool calling.
- **Twin-Soul runtime**: tách hai agent độc lập: `march7` cho hội thoại chính, `evernight` cho chat riêng + tác vụ nền.
- **Evernight Discord bot**: có thể nhận DM, tag/mention hoặc prefix `!9` để trò chuyện, đồng thời gửi DM thông báo/approval khi Bảy cần báo việc hoặc xin phép chạy hành động.
- **Memory 3 tầng**: T1 Redis-backed active memory, T2 Redis Stack semantic/vector memory, T3 Markdown profile.
- **Background consolidation**: tự động tổng hợp hội thoại khi inactivity/overflow.
- **Self-heal loop**: có sẵn khung, đang tiếp tục phát triển.

## Dành cho maintainer/agent

Nếu bạn đang dùng agent để làm việc trong repo (đọc kiến trúc, cách chạy, workflow, testing, quy ước code…), hãy bắt đầu ở:

- [`.agents/README.md`](.agents/README.md) (index + CodeGraph policy)

Bộ tài liệu này giúp agent nắm đúng boundary (Bash Executor/A2A), cách chạy Docker/local, và checklist review.

## Kiến trúc tổng quan

```text
Discord
  -> March7 bot: chat chính, tool calling, T1/T3
  -> Evernight bot: DM/tag/!9 chat, notification, approval, self-heal

March7 <-> Evernight: A2A boundary
Memory: T1 active + T2 semantic/wiki + T3 profile
```

| Agent | Vai trò | Port |
|-------|---------|------|
| **March7** | Trợ lý chính — chat, tool calling, quản lý T1/T3 | 8000 |
| **Evernight** | Agent độc lập — DM/tag/prefix chat, notification/approval, self-healing, giám sát lỗi, consolidation T2 | 8001 |

Hai agent giao tiếp qua A2A (HTTP JSON-RPC + SSE). Evernight phải truy cập memory của March7 qua boundary A2A (`get_snapshot`, `clear_session`), không đọc trực tiếp T1 keys của March7.

### Luồng tổng quát

```mermaid
flowchart LR
    D[Discord] --> M[March7 bot]
    D --> E[Evernight bot]
    M <--> A[A2A boundary]
    A <--> E
    M --> T1[(T1 active memory)]
    M --> T3[(T3 profile)]
    E --> T2[(T2 semantic/wiki memory)]
```

---

## Plan cần đọc

- [Unified Discussion Memory Plan](docs/plans/unified-discussion-memory.md): kế hoạch thống nhất T1 + T2 cho cả 1-1 user chat lẫn multi-user channel discussion. T1 scope-aware (user/channel), T2 user-centric fan-out (bot nhớ theo user, channel chỉ là metadata). Thay flow `TOKEN_LIMIT_REACHED → overflow_queue` cũ bằng `SUMMARY_REQUESTED → DiscussionConsolidator → SUMMARY_COMPLETED → cleanup`.

Ghi chú dễ quên:

- Evernight là agent độc lập: có thể DM/tag/`!9` để trò chuyện và gửi thông báo/approval.
- Channel memory chỉ observe channel được phép, không nghe toàn server. Reply trigger gồm cả reply-to-bot (không chỉ mention).
- T2 user-centric: `T2Page.user_id` luôn là real user_id (digit). Channel info nằm trong `source_refs`.
- DiscussionConsolidator fan-out cho mỗi `active_participant` (LLM quyết định).
- T1 không xóa raw entries cho tới khi nhận `SUMMARY_COMPLETED`.

## Cấu trúc thư mục chính

- `gateway/`: adapter + router cho platform (Discord).
- `twin/march7/`: agent hội thoại chính.
- `twin/evernight/`: Evernight agent độc lập (DM/tag/prefix chat, notification/approval, consolidation, self-heal).
- `twin/shared/`: A2A, LLM adapters, memories/tools dùng chung.
- `docker/`: compose + Dockerfiles cho toàn hệ thống.
- `tests/`: unit/integration/e2e/manual tests.

## Prerequisites

- Python `3.11+`
- Docker + Docker Compose v2
- Discord bot token(s)
- API key cho LLM provider

## Quick start

---

### 1) Docker (khuyến nghị)

```bash
cd docker
docker compose down
DOCKER_BUILDKIT=1 docker compose build
docker compose up -d
docker compose logs -f
```

### 2) Local Python

```bash
pip install -r requirements.txt
python -m gateway
# hoặc chạy từng agent:
python -m twin.march7
python -m twin.evernight
```

---

> [!TIP]
> Health endpoints kỳ vọng:
> - `http://localhost:8000/.well-known/agent.json`
> - `http://localhost:8001/.well-known/agent.json`

## Cấu hình

---

Các nhóm biến chính (chi tiết ở `.agents/PROJECT_CONTEXT.md`):

- Shared: `REDIS_URL`, `CODEBOX_API_URL`, `BASH_EXECUTOR_URL`, `T1_STORAGE_PHASE`
- March7: `MARCH7_A2A_PORT`, `MARCH7_REDIS_DB`, `MARCH7_PERSONA_PATH`
- Evernight: `EVERNIGHT_A2A_PORT`, `EVERNIGHT_REDIS_DB`, `INACTIVITY_SECONDS`, `SELF_HEAL_ENABLED`
- Discord/Gateway: `DISCORD_MARCH7_TOKEN`, `DISCORD_EVERNIGHT_TOKEN`, `GATEWAY_ENABLED_PLATFORMS`

`T1_STORAGE_PHASE` chọn storage T1:

- `legacy`: Redis basic/HASH path, hiện là path ổn định cho T1.
- `redis_stack`: Redis Stack JSON/Search adapter, dùng thử nghiệm hoặc cutover sau khi parity test ổn.

> [!NOTE]
> Runtime Redis trong Docker dùng `redis/redis-stack-server`, nên cùng một Redis Stack service có thể phục vụ cả T1 và T2. T1 không bắt buộc dùng JSON/Search; T2 mới là tầng semantic/vector cần Redis Stack features.

T1 chat context dùng recent-window theo token budget:

- `T1_CONTEXT_MAX_TOKENS`: số token T1 tối đa đưa vào prompt chat.
- `T1_CONTEXT_MAX_MESSAGES`: hard cap số message gần nhất.

LLM/embeddings: xem `README_LLM_PROVIDERS.md` (hỗ trợ OpenAI-compat + Gemini native qua factory pattern ở `twin/shared/llm/embedding/`).

## Development & testing

```bash
pytest tests/unit/ -v
pytest tests/integration/ -v
pytest tests/e2e/ -v
```

## Tài liệu liên quan

- `.agents/PROJECT_CONTEXT.md`
- `.agents/AGENT_RULES.md`
- `.agents/TESTING_GUIDE.md`
- `README_LLM_PROVIDERS.md`
- `README_BASH_EXECUTOR.md`
- `docker/README.md`

## Troubleshooting nhanh

> [!WARNING]
> Bash Executor là tool đặc quyền. Chỉ bật khi cần và luôn giữ luồng approve theo `README_BASH_EXECUTOR.md`.

- Kiểm tra trạng thái containers: `docker compose -f docker/docker-compose.yml ps`
- Xem logs: `docker compose -f docker/docker-compose.yml logs -f march7 evernight`
- Kiểm tra A2A health endpoints ở cổng `8000` và `8001`
