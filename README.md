# Bé Bảy (March7) — Twin-Soul AI Assistant for Discord

Bé Bảy là hệ Twin-Soul AI trên Discord: `march7` là agent hội thoại chính, `evernight` là agent độc lập vừa trò chuyện qua DM/tag/prefix vừa làm background consolidation, notification, self-heal. Hai agent giao tiếp qua A2A.

## Tính năng chính

- **Discord AI assistant**: hội thoại tự nhiên + tool calling.
- **Twin-Soul runtime**: `march7` cho chat chính, `evernight` cho chat riêng + tác vụ nền.
- **Evernight DM/tag/!9**: nhận DM, tag/mention, prefix `!9`; gửi DM thông báo/approval.
- **Memory 3 tầng**: T1 Redis active, T2 `TimelineSummaryStore` (vector search), T3 Markdown profile.
- **Background consolidation**: tự động tổng hợp thông qua A2A Consolidation (`March7` gọi `Evernight`).
- **Self-heal loop**: framework có sẵn, đang phát triển.

## Yêu cầu cho agent workflow

Repo này tối ưu cho agent (Claude Code, Antigravity, Cursor, ...). Trước khi để agent đụng vào, cài đặt 2 thứ:

1. **CodeGraph** — index AST của repo, agent dùng cho mọi câu hỏi structural (where is X, what calls Y, impact of Z, ...). Skills đều giả định CodeGraph có sẵn.
   ```bash
   npm install -g @colbymchenry/codegraph
   codegraph init -i      # chạy 1 lần trong repo, tạo .codegraph/
   ```
2. **Skills toàn cục** — 6 skill (`implementation-planner`, `thoughtful-coder`, `debug-investigator`, `code-reviewer`, `architecture-docs`, `create-readme`) ở [Flowerf19/agents-skills](https://github.com/Flowerf19/agents-skills). Clone 1 lần, dùng cho mọi project:
   ```bash
   git clone https://github.com/Flowerf19/agents-skills.git ~/.claude/skills
   ```
   Claude Code auto-discover qua `/<skill-name>`; agent khác point thẳng vào `~/.claude/skills/<name>/SKILL.md`.

Agent docs project-specific (boundary A2A, gotcha runtime, testing) ở [.agents/](.agents/) — bắt đầu đọc từ [.agents/README.md](.agents/README.md).

## Kiến trúc tổng quan

```mermaid
flowchart LR
    D[Discord] --> M[March7 bot]
    D --> E[Evernight bot]
    M -- "A2A Task (port 8001)<br/>consolidate_discussion" --> E
    M --> S[(Shared memory stack)]
    E --> S
    S --> T1[(T1 active memory)]
    S --> T2[(T2 timeline/vector)]
    S --> T3[(T3 profile)]
```

| Agent | Vai trò | Port |
|---|---|---|
| **March7** | Chat chính, tool calling, T1/T2/T3 shared memory | 8000 |
| **Evernight** | DM/tag/`!9` chat, notification/approval, self-heal, T1/T2/T3 shared memory | 8001 |

Evernight nhận tác vụ xử lý tóm tắt trí nhớ (Consolidation) từ March7 qua A2A (`consolidate_discussion`), truy cập T1 để tóm tắt và ghi xuống T2/T3.

### Memory 3 tầng — tại sao & vòng đời

Hai agent chia nhau **một stack memory duy nhất**, tách 3 tầng vì mỗi tầng phục vụ một *latency budget* khác nhau: hot-path phải nhanh, semantic recall chạy async, profile thì biên dịch sẵn. Toàn bộ local-first (LLM + embeddings self-hosted qua LM Studio), không phụ thuộc cloud.

- **T1 — active (working memory ngắn hạn):** cửa sổ trượt các message gần nhất theo từng scope (1-1 user hoặc channel) trong Redis. Nạp thẳng vào context mỗi lượt chat. Ngưỡng token kích hoạt consolidation; sau khi tổng hợp, T1 bị cắt bớt nhưng giữ lại phần đuôi gần nhất để giữ mạch hội thoại.
- **T2 — timeline (semantic memory dài hạn), trên Redis Stack:** Lưu trữ các snapshot tóm tắt quá trình trò chuyện dưới dạng `TimelineSummary` (Redis HASH với vector embedding). Truy hồi ngữ nghĩa qua KNN vector search (`TimelineSummaryStore.search`).
- **T3 — profile:** một markdown profile các section cố định được cập nhật trực tiếp sau mỗi chu kỳ tóm tắt, sau đó inject vào system prompt mỗi lượt. Profile lưu giữ các fact cốt lõi một cách cô đọng.

**Vòng đời (A2A Consolidation):**
Hệ thống sử dụng cơ chế A2A trực tiếp thay vì các pipeline tuần tự phức tạp trước đây (Extractor/Curator/Topic):
1. **Observe:** `March7` nhận tin nhắn và lưu vào `T1 ActiveMemory`.
2. **Trigger:** `InactivityTrigger` (hiện được quản lý hoàn toàn bởi `Evernight`, đã gỡ khỏi gateway của `March7`) theo dõi tính trạng idle. Khi thỏa điều kiện hoặc T1 đạt ngưỡng, một tác vụ `consolidate_discussion` được sinh ra. Đối với March7, nó dùng `ConsolidationClient` (qua port 8001) gửi yêu cầu sang `Evernight`.
3. **Consolidate:** `Evernight` nhận yêu cầu (hoặc tự trigger) và chạy `ConsolidateMemoryTool`. Tool này gọi LLM để đọc toàn bộ T1 snapshot, sau đó tạo ra cả bản tóm tắt T2 (`TimelineSummaryStore`) và bản cập nhật T3 (`MarkdownProfileStore`) trong cùng một lượt, rồi lưu trực tiếp vào DB.
4. **Trim:** T1 được tự động cắt bớt phần cũ để giải phóng context window. Cơ chế chi tiết có thể xem tại `twin/shared/memory/` và qua CodeGraph.

### Plan trạng thái

- [Memory Rewrite](.agents/plans/memory-rewrite.md) — T1/T2/T3 chạy qua `twin/shared/memory/`, T2 dùng Redis Stack VECTOR HNSW 1024, T3 là Markdown 8 section. **Tiến độ: Phase 11/11 ✓**.
- Unified Discussion Memory: đã được hấp thụ vào memory rewrite; flow hiện tại dùng hoàn toàn cơ chế **A2A Consolidation** (InactivityTrigger → ConsolidateMemoryTool), thay thế hoàn toàn `SharedMemoryManager → Consolidator → DebouncedScheduler` cũ.

### Gotcha runtime (dễ quên)

- Channel memory chỉ observe channel được phép, không nghe toàn server. Reply trigger gồm cả reply-to-bot.
- T2 timeline là user-centric: channel scope **extract 1 lần** rồi route mỗi memory về đúng participant nó nói về (`subject_user_id`), **không** fan-out per-author; Redis document dùng `user_id` thật (của subject) làm key trong `TimelineSummaryStore`.
- Redis Stack RediSearch index phải ở DB 0; dùng `TIMELINE_REDIS_DB=0` cho T2, còn T1 có thể dùng DB riêng theo agent.
- T3 profile inject vào system prompt mỗi turn qua `MarkdownProfileStore.get_system_prompt_context()`.

### Host bash tool — 2 lớp chặn

`execute_host_bash` là proxy tool: chạy trong container nhưng thực thi trên host qua HTTP. Vì là tool đặc quyền, mỗi lần gọi đi qua **2 lớp chặn độc lập** — duyệt người (gateway cấp context + nút approve) *trước*, rồi xác thực caller (`Origin` allowlist) ở host. Thiếu bất kỳ lớp nào → lệnh dừng, không bao giờ chạm `bash`.

```mermaid
flowchart LR
    subgraph C["Container (march7-bot)"]
        LLM[March7 LLM] --> T[execute_host_bash]
        T --> G{"Trạm Gác<br/>ApprovalGate<br/>— LỚP A"}
        G -->|reject / timeout / no context| RA["❌ từ chối bởi Trạm Gác"]
    end
    G -->|approved<br/>Origin: march7-bot| O{"Origin allowlist<br/>— LỚP B"}
    subgraph H["Host (Bash Executor :8374)"]
        O -->|Origin lạ / thiếu| RB["❌ 403 Forbidden"]
        O -->|hợp lệ| X["nsenter → bash -c"]
        X --> R["stdout / stderr / exit_code"]
    end
```

| | Lớp A — Trạm Gác | Lớp B — Origin |
|---|---|---|
| **Vị trí** | Trong container, *trước* HTTP | Trên host, *đầu* `/execute` |
| **Chặn ai** | Lệnh chưa được người duyệt | Caller không phải bot container |
| **Cơ chế** | `ApprovalGate` + `ApprovalBackend` (nút Discord) do **gateway** cấp qua context | So `Origin` header với `BASH_EXECUTOR_ALLOWED_ORIGINS` |
| **Bỏ qua** | env `APPROVAL_AUTO_APPROVE_WITHOUT_CONTEXT=true` | thêm origin vào allowlist |

> [!NOTE]
> "Gateway chặn" = dừng ở Lớp A: gateway là nơi set approval context/backend. Message **không** đi qua gateway adapter → không có bề mặt xin phép → mặc định `reject`.

## Prerequisites

- Python `3.11+`
- Docker + Docker Compose v2
- Discord bot token(s) + API key LLM provider

## Quick start

**Docker (khuyến nghị):**

```bash
cd docker
docker compose down
DOCKER_BUILDKIT=1 docker compose build
docker compose up -d
docker compose logs -f
```

**Local Python:**

```bash
pip install -r requirements.txt
python -m gateway
# hoặc:
python -m twin.march7
python -m twin.evernight
```

> [!TIP]
> Health: `http://localhost:8000/.well-known/agent.json`, `http://localhost:8001/.well-known/agent.json`.

## Cấu hình

Nhóm env vars chính (chi tiết ở [.agents/PROJECT_CONTEXT.md](.agents/PROJECT_CONTEXT.md)):

- Shared: `REDIS_URL`, `TIMELINE_REDIS_DB`, `CODEBOX_API_URL`, `BASH_EXECUTOR_URL`
- March7: `MARCH7_A2A_PORT`, `MARCH7_REDIS_DB`, `MARCH7_PERSONA_PATH`
- Evernight: `EVERNIGHT_A2A_PORT`, `EVERNIGHT_REDIS_DB`, `POLL_INTERVAL`, `SELF_HEAL_ENABLED`
- Discord/Gateway: `DISCORD_MARCH7_TOKEN`, `DISCORD_EVERNIGHT_TOKEN`, `GATEWAY_ENABLED_PLATFORMS`
- T1 budget: `T1_CONTEXT_MAX_TOKENS`, `T1_CONTEXT_MAX_MESSAGES`
- Embeddings/T2: `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL_NAME`, `EMBEDDING_VECTOR_SIZE=1024`

> [!NOTE]
> Docker dùng `redis/redis-stack-server` — cùng service phục vụ cả T1 và T2.

LLM + embeddings (OpenAI-compat / Gemini native qua factory): xem [twin/shared/llm/README.md](twin/shared/llm/README.md).

## Development & testing

```bash
pytest tests/unit/ -v
pytest tests/integration/ -v
pytest tests/e2e/ -v
```

## Troubleshooting

> [!WARNING]
> Bash Executor là tool đặc quyền. Bật khi cần và giữ luồng approve theo [scripts/README.md](scripts/README.md).

- Trạng thái containers: `docker compose -f docker/docker-compose.yml ps`
- Logs: `docker compose -f docker/docker-compose.yml logs -f march7 evernight`
- A2A health: port `8000` và `8001`

## Tài liệu liên quan

- [.agents/](.agents/) — agent guidance (start: [README.md](.agents/README.md))
- [twin/shared/llm/README.md](twin/shared/llm/README.md) — LLM + embedding config
- [scripts/README.md](scripts/README.md) — bash executor security
- [docker/README.md](docker/README.md) — Docker runbook
