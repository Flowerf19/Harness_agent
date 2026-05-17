# PROJECT_CONTEXT

Mục tiêu: mô tả **dự án chạy như thế nào** theo kiến trúc hiện tại, và môi trường nào dùng cho việc gì.

## Chế độ chạy (ưu tiên)

### 1) Docker Compose (primary / khuyến nghị)

Repo có cấu trúc Docker rõ ràng trong [docker/](../docker/).

- Master compose: [docker/docker-compose.yml](../docker/docker-compose.yml) (gồm các include trong `docker/shared/` và service agents).
- Tài liệu vận hành: [docker/README.md](../docker/README.md)

Các service chính (tổng hợp từ `docker/README.md`):

- `redis` (T1 + coordination)
- `qdrant` (T2 Wiki Pages)
- `codebox` (sandbox chạy code Python)
- `bash-executor` (host command execution, có approval)
- `march7` (Gateway + March7 Discord bot + March7 A2A)
- `evernight` (Evernight bot + consolidation + self-healing)

Ports thường gặp:

- March7 A2A: `8000`
- Evernight A2A: `8001`
- Qdrant: `6333`
- Codebox: `8069`
- Bash Executor: `8374`

Health endpoints (kỳ vọng):

- `http://localhost:8000/.well-known/agent.json`
- `http://localhost:8001/.well-known/agent.json`

### 2) Local Python (secondary)

Khi không cần Docker, có thể chạy local:

- Gateway: `python -m gateway`
- March7 standalone: `python -m twin.march7`
- Evernight standalone: `python -m twin.evernight`

Dependencies: `requirements.txt`.

Lưu ý: integration/e2e thường vẫn cần Redis/Qdrant chạy (local hoặc docker).

### 3) Conda env `discord_bot` (test-only)

Thư mục `docker/volumes/conda_envs/discord_bot/` thể hiện có môi trường conda phục vụ **test/dev cục bộ**.

- Đây **không** phải runtime chính của dự án.
- Khi viết hướng dẫn hoặc task, coi đây là tùy chọn phụ để reproduce môi trường test.

## Nhóm biến môi trường (tóm tắt)

Nguồn tham chiếu chính: [gateway/config.py](../gateway/config.py), [twin/march7/config.py](../twin/march7/config.py), [twin/evernight/config.py](../twin/evernight/config.py), và [docker/ARCHITECTURE.md](../docker/ARCHITECTURE.md).

### Shared (hạ tầng/LLM)

- `REDIS_URL`
- `QDRANT_URL`
- `CODEBOX_API_URL`
- `BASH_EXECUTOR_URL`
- `LLM_PROVIDER` / các biến liên quan provider (Qwen/OpenAI/Gemini…)

### March7

- `MARCH7_A2A_PORT` (default 8000)
- `MARCH7_REDIS_DB` (default 0)
- `MARCH7_PERSONA_PATH` (default `twin/march7/personas`)

### Evernight

- `EVERNIGHT_A2A_PORT` (default 8001)
- `EVERNIGHT_REDIS_DB` (default 1)
- `EVERNIGHT_PERSONA_PATH` (default `twin/evernight/personas`)
- `MARCH7_URL` (Evernight → March7, default `http://march7:8000`)
- `INACTIVITY_SECONDS` (default 1800)
- `POLL_INTERVAL` (default 60)
- `SELF_HEAL_ENABLED` (default true)

### Discord / Gateway

- `GATEWAY_ENABLED_PLATFORMS` (default `discord`)
- `DISCORD_GATEWAY_ENABLED` (default true)
- `DISCORD_MARCH7_TOKEN`
- `DISCORD_EVERNIGHT_TOKEN`

## Tooling & risk notes

- Bash Executor: xem [README_BASH_EXECUTOR.md](../README_BASH_EXECUTOR.md).
- Docker ownership boundary map: xem [docker/ARCHITECTURE.md](../docker/ARCHITECTURE.md).
