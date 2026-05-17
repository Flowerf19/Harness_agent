# Docker Setup — March7

> **Dành cho agent (Copilot/LLM)**: Trước khi làm việc với Docker, đọc [.agents/README.md](../.agents/README.md) để nắm kiến trúc, boundary, và workflow.

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
│   ├── │   ├── docker-compose.codebox.yml
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
    ├── redis_data/              # Redis AOF/RDB — T1, T2, coordination, queue    └── hf_cache/                # HuggingFace embedding models
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
| `evernight` | `evernight` | `evernight-agent` | 8001 | Evernight Discord bot + consolidation + self-healing |

Xem [ARCHITECTURE.md](ARCHITECTURE.md) để biết ranh giới service nào là private và service nào dùng chung.

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

### From project root

```bash
docker compose -f docker/docker-compose.yml up -d
docker compose -f docker/docker-compose.yml logs -f
```

### Individual service operations

```bash
# Chỉ start infrastructure
docker compose -f docker/shared/docker-compose.redis.yml \               -f docker/shared/docker-compose.codebox.yml up -d

# Start riêng agents
docker compose -f docker/docker-compose.yml up -d march7 evernight

# Rebuild một service
DOCKER_BUILDKIT=1 docker compose -f docker/docker-compose.yml build march7
```

## Data Persistence

Tất cả dữ liệu lưu trong `docker/volumes/` qua bind mounts:

| Directory | Purpose | Storage |
|-----------|---------|---------|
| `redis_data/` | T1 Active Memory | Redis AOF (append-only file) || `hf_cache/` | Embedding models | HuggingFace cache (~500MB) |

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

# LLM
LLM_PROVIDER=qwen
LLM_MODEL=qwen3.6-max-preview
TOOL_LLM_ENDPOINT=http://host.docker.internal:1234/v1

# Infrastructure (internal Docker network)
REDIS_URL=redis://redis:6379
CODEBOX_API_URL=http://codebox:8069
```
