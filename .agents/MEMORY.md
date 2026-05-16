# MEMORY (Repo facts)

File này lưu **facts đã xác minh** về repo để agent dùng lâu dài.

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

- File: `docker/docker-compose.yml`
- Includes shared infra: redis/qdrant/codebox/bash-executor + agent services.

## Needs verification / follow-ups

- Lint/format/type tooling: hiện không thấy config ở root; nếu repo có conventions khác, cập nhật file này.
