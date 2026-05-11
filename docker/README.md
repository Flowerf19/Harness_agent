# Docker Setup — March7

## Structure

```
docker/
├── docker-compose.yml           # Master compose (network + includes)
├── docker-compose.redis.yml     # Redis (T1 Active Memory)
├── docker-compose.qdrant.yml    # Qdrant (T2 Wiki Pages)
├── docker-compose.codebox.yml   # CodeBox sandbox
├── docker-compose.bot.yml       # Gateway + Twin Agents
├── docker-compose.bash-executor.yml  # Bash executor on host
│
├── Dockerfile                   # Legacy multi-stage build (đang migrate)
├── shared/Dockerfile.base       # Base image cho tất cả services
├── gateway/Dockerfile           # Gateway orchestrator
├── march7/Dockerfile            # March7 Agent (trợ lý chính)
├── evernight/Dockerfile         # Evernight Agent (self-healing)
├── twin/Dockerfile              # Twin agents combined
│
├── bash-executor.service        # systemd unit cho bash executor
├── bash-executor-starter.service
├── README.md                    # This file
│
└── volumes/                     # Persistent data (bind mounts)
    ├── redis_data/              # Redis AOF — T1 Active Memory
    ├── qdrant_data/             # Qdrant vectors — T2 Wiki Pages
    └── hf_cache/                # HuggingFace embedding models
```

## Architecture

### Twin-Soul Agent Services

| Service | Container | Image | Port | Purpose |
|---------|-----------|-------|------|---------|
| `redis` | `march7_redis` | `redis:alpine` | 6379 | T1 Active Memory + Queue |
| `qdrant` | `march7_qdrant` | `qdrant/qdrant` | 6333 | T2 Wiki Pages (semantic search) |
| `codebox` | `march7_codebox` | `codebox` | 8069 | Python sandbox |
| `gateway` | `march7_gateway` | `march7_gateway` | — | Discord → A2A routing |
| `march7` | `march7_agent` | `march7_agent` | 8000 | Trợ lý chính (A2A endpoint) |
| `evernight` | `evernight_agent` | `evernight_agent` | 8001 | Self-healing + Consolidation (A2A endpoint) |

Kiến trúc tuân theo taste rule: **mỗi service Dockerfile riêng biệt, không gom chung**.

### Multi-stage Build (Dockerfile.base)

- **shared/Dockerfile.base**: Base image với Python 3.11 + uv + dependencies chung
- **gateway/Dockerfile**, **march7/Dockerfile**, **evernight/Dockerfile**: Kế thừa base image, thêm code riêng
- **twin/Dockerfile**: Build gộp cả March7 + Evernight (cho development)

### Legacy Dockerfile

`Dockerfile` ở root docker/ là legacy multi-stage build cho bot đơn luồng cũ. Đang được migrate sang các Dockerfile mới trong `gateway/`, `march7/`, `evernight/`.

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
docker compose -f docker/docker-compose.redis.yml \
               -f docker/docker-compose.qdrant.yml \
               -f docker/docker-compose.codebox.yml up -d

# Start riêng gateway + agents
docker compose -f docker/docker-compose.bot.yml up -d

# Rebuild một service
DOCKER_BUILDKIT=1 docker compose -f docker/docker-compose.bot.yml build march7
```

## Data Persistence

Tất cả dữ liệu lưu trong `docker/volumes/` qua bind mounts:

| Directory | Purpose | Storage |
|-----------|---------|---------|
| `redis_data/` | T1 Active Memory | Redis AOF (append-only file) |
| `qdrant_data/` | T2 Wiki Pages | Qdrant vectors + payload |
| `hf_cache/` | Embedding models | HuggingFace cache (~500MB) |

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
docker compose logs -f gateway    # Gateway
docker compose logs -f            # All

# Restart
docker compose restart march7

# Exec
docker exec -it march7_agent bash
docker exec -it evernight_agent bash

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
DISCORD_LLM_BOT_TOKEN=your_bot_token
DISCORD_LLM_BOT_CLIENT_ID=your_client_id

# Gateway
GATEWAY_ENABLED_PLATFORMS=discord
DISCORD_GATEWAY_ENABLED=true

# LLM
LLM_PROVIDER=qwen
LLM_MODEL=qwen3.6-max-preview
TOOL_LLM_ENDPOINT=http://host.docker.internal:1234/v1

# Infrastructure (internal Docker network)
REDIS_URL=redis://redis:6379
QDRANT_URL=http://qdrant:6333
CODEBOX_API_URL=http://codebox:8069
```
