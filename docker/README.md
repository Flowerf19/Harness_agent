# Docker Setup — March7

> **Dành cho agent (Copilot/LLM)**: Trước khi làm việc với Docker, đọc [.agents/README.md](../.agents/README.md) để nắm kiến trúc, boundary, và workflow.

## Mục tiêu

Docker Compose là runtime chính cho kiến trúc Twin-Soul của dự án:

- `march7`: main chat runtime + gateway + A2A `:8000`
- `evernight`: independent Discord agent for DM/tag/`!9` chat, notifications/approvals, consolidation/self-heal + A2A `:8001`
- shared infra: Redis, Codebox, Bash Executor

## Structure

```
docker/
├── docker-compose.yml           # Master compose (network + includes)
│
├── shared/
│   ├── Dockerfile.base
│   ├── Dockerfile.bash-executor
│   ├── docker-compose.base.yml
│   ├── docker-compose.redis.yml
│   ├── docker-compose.codebox.yml
│   ├── docker-compose.bash-executor.yml
│   ├── bash-executor.service
│   └── bash-executor-starter.service
├── march7/
│   ├── Dockerfile
│   └── docker-compose.yml
├── evernight/
│   ├── Dockerfile
│   └── docker-compose.yml
│
├── README.md                    # This file
│
└── volumes/                     # Persistent data (bind mounts)
    └── redis_data/              # Redis AOF/RDB — T1 + coordination
```

## Architecture

### Twin-Soul Agent Services

| Service | Container | Image | Port | Purpose |
|---------|-----------|-------|------|---------|
| `redis` | `march7-redis` | `redis/redis-stack-server` | 6379 | Shared T1 storage + coordination markers |
| `codebox` | `march7-codebox` | `shroominic/codebox` | 8069 | Python sandbox |
| `bash-executor` | `march7-bash-executor` | `march7-bash-executor` | 8374 | Shared privileged host executor |
| `base` | — | `march7-base` | — | Shared Python runtime |
| `march7` | `march7` | `march7-agent` | 8000 | Gateway + March7 Discord bot + March7 A2A |
| `evernight` | `evernight` | `evernight-agent` | 8001 | Evernight Discord bot for DM/tag/`!9` chat, notifications/approvals, consolidation + self-healing |

Xem [ARCHITECTURE.md](ARCHITECTURE.md) để biết boundary private/shared chi tiết.

> [!WARNING]
> Evernight không đọc trực tiếp T1 keys của March7; truy cập memory qua A2A boundary (`get_snapshot`, `clear_session`).

### Current Build

- **shared/Dockerfile.base**: runtime Python + dependencies chung.
- **march7/Dockerfile**: March7-owned image, entrypoint `python -m gateway`.
- **evernight/Dockerfile**: Evernight-owned image, entrypoint `python -m twin.evernight`.

### Tool Images

`shared/Dockerfile.bash-executor` builds the `bash-executor` tool image. Shared tool containers use hyphenated Docker names, while Python files keep snake_case module names.

## Quick Start

### Clean start (first time or after changes)

```bash
cd docker
docker compose down
DOCKER_BUILDKIT=1 docker compose build
docker compose up -d
docker compose logs -f
```

Health endpoints sau khi chạy:

- `http://localhost:8000/.well-known/agent.json`
- `http://localhost:8001/.well-known/agent.json`

### From project root

```bash
docker compose -f docker/docker-compose.yml up -d
docker compose -f docker/docker-compose.yml logs -f
```

### Individual service operations

```bash
# Chỉ start infrastructure
docker compose -f docker/shared/docker-compose.redis.yml \
    -f docker/shared/docker-compose.codebox.yml up -d

# Start riêng agents
docker compose -f docker/docker-compose.yml up -d march7 evernight

# Rebuild một service
DOCKER_BUILDKIT=1 docker compose -f docker/docker-compose.yml build march7
```

## Data Persistence

Tất cả dữ liệu lưu trong `docker/volumes/` qua bind mounts:

| Directory | Purpose | Storage |
|-----------|---------|---------|
| `redis_data/` | T1 + coordination | Redis AOF/RDB |

## Commands Reference

```bash
# Start all
docker compose up -d

# Stop all
docker compose down

# Stop + remove volumes (⚠️ xóa toàn bộ dữ liệu)
docker compose down -v

# Rebuild tất cả
DOCKER_BUILDKIT=1 docker compose build

# Logs
docker compose logs -f march7     # March7 agent
docker compose logs -f evernight  # Evernight agent
docker compose logs -f            # All

# Restart
docker compose restart march7

# Exec
docker exec -it march7 bash
docker exec -it evernight bash

# Health check
docker compose ps
```

## Hot-Reload

Code changes trong `twin/`, `gateway/`, hoặc `memories/` được watch tự động bởi `watchmedo` — không cần rebuild container.

Chỉ rebuild image khi:
- Thay đổi `requirements.txt` (dependencies mới)
- Sửa Dockerfile

## Environment Variables

Bot service đọc từ `../.env`. Key variables:

```env
# Discord
DISCORD_MARCH7_TOKEN=your_march7_bot_token
DISCORD_MARCH7_CLIENT_ID=your_march7_client_id
DISCORD_EVERNIGHT_TOKEN=your_evernight_bot_token

# Gateway
GATEWAY_ENABLED_PLATFORMS=discord
DISCORD_GATEWAY_ENABLED=true

# LLM chat
LLM_PROVIDER=openai
OPENAI_API_URL=http://host.docker.internal:11434/v1
OPENAI_API_KEY=dummy-key
OPENAI_MODEL=your-model

# Embeddings
EMBEDDING_PROVIDER=openai
EMBEDDING_API_URL=http://host.docker.internal:11434/v1
EMBEDDING_API_KEY=dummy-key
EMBEDDING_MODEL_NAME=your-embedding-model
EMBEDDING_VECTOR_SIZE=1024

# Infrastructure (internal Docker network)
REDIS_URL=redis://redis:6379
TIMELINE_REDIS_DB=0
CODEBOX_API_URL=http://codebox:8069
```

## Redis Stack Notes

T1 active memory can use each agent's own Redis DB (`MARCH7_REDIS_DB`,
`EVERNIGHT_REDIS_DB`). T2 timeline memory uses RediSearch indexes and must run
on Redis DB 0, so compose sets `TIMELINE_REDIS_DB=0` for both agents.

> [!TIP]
> Chi tiết provider và mapping endpoint xem `../twin/shared/llm/README.md`.
