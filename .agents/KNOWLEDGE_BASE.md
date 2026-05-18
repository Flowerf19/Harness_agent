# KNOWLEDGE_BASE

Tài liệu gộp: **MEMORY.md** (facts đã verify) + **GLOSSARY.md** (thuật ngữ).

## Verified facts

### Entrypoints

- Gateway: `python -m gateway`
- March7: `python -m twin.march7` (A2A default `:8000`)
- Evernight: `python -m twin.evernight` (A2A default `:8001`)

### Config defaults (from code)

- March7:
  - `MARCH7_A2A_PORT=8000`
  - `MARCH7_REDIS_DB=0`
  - `MARCH7_PERSONA_PATH=twin/march7/personas`
- Evernight:
  - `EVERNIGHT_A2A_PORT=8001`
  - `EVERNIGHT_REDIS_DB=1`
  - `EVERNIGHT_PERSONA_PATH=twin/evernight/personas`
  - `MARCH7_URL=http://march7:8000`
  - `INACTIVITY_SECONDS=1800`, `POLL_INTERVAL=60`

### T3 Core Memory storage

- Storage format: **Markdown**
- Storage class: `MarkdownStorage`
- Default base path: `memories/` (writes `memories/{user_id}.md`)

### Docker master compose

- File: [docker/docker-compose.yml](../docker/docker-compose.yml)
- Includes shared infra: redis/codebox/bash-executor + agent services.

## Glossary

### Twin-Soul Agents

- **March7**: agent hội thoại chính (chat/tool calling/memory T1/T3).
- **Evernight**: agent background (consolidation/self-heal/triggers).

### Memory tiers

- **T1 (Active Memory)**: ngữ cảnh ngắn hạn; Redis.
- **T2 (Wiki Pages / Episodic Memory)**: tri thức dài hạn; Redis Stack.
- **T3 (Core Memory)**: hồ sơ user; Markdown files.

### Consolidation

Quá trình gom hội thoại (T1 snapshot) thành tri thức T2 (wiki pages), thường do Evernight chạy khi user inactivity.

### A2A

Agent-to-Agent protocol (HTTP JSON-RPC + SSE) để March7 và Evernight gọi nhau qua network boundary.

### Gateway / Adapter / Handler / Router

- **Adapter**: tích hợp nền tảng (Discord).
- **Handler**: áp rules/filtering, context platform.
- **Router**: quyết định gửi message/tác vụ sang agent nào.

### Codebox

Service sandbox chạy code Python.

### Bash Executor

Tool chạy lệnh bash trên host; yêu cầu approval; rủi ro cao nếu bị prompt injection.

## Needs verification / follow-ups

- Lint/format/type tooling: hiện không thấy config ở root; nếu repo có conventions khác, cập nhật file này.
