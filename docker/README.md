# Docker Setup — March7

## Structure

```
docker/
├── Dockerfile                  # Multi-stage build with uv
├── docker-compose.yml           # Master file (network + includes)
├── docker-compose.redis.yml     # Redis service
├── docker-compose.qdrant.yml    # Qdrant service
├── docker-compose.codebox.yml   # CodeBox sandbox
├── docker-compose.bot.yml       # March7 bot application
├── .dockerignore                # Build context exclusions
├── README.md                    # This file
└── volumes/                     # Persistent data (bind mounts)
    ├── redis_data/              # Redis - Active Memory (T1)
    ├── qdrant_data/             # Qdrant - Episodic Memory (T2)
    └── hf_cache/                # HuggingFace model cache
```

## Architecture

### Multi-stage Dockerfile
- **Stage 1 (Builder):** `python:3.11-slim` + `uv` for fast package installation with cache mounts
- **Stage 2 (Runtime):** Minimal image with non-root `march7_user`, copies venv from builder
- **Entry point:** `ENTRYPOINT_CMD=gateway` (default) → `python -m gateway`; `ENTRYPOINT_CMD=src` → `python src/bot.py`
- **Hot-reload:** `watchmedo auto-restart` watches `./gateway` and `./src` for `.py` changes

### Modular Docker Compose
Each service lives in its own file for clarity. The master `docker-compose.yml` includes them all via the `include` directive (Docker Compose v2+).

| File | Service | Container | Limits |
|------|---------|-----------|--------|
| `docker-compose.redis.yml` | Redis | `march7_redis` | 512M memory |
| `docker-compose.qdrant.yml` | Qdrant | `march7_qdrant` | 1G memory, 1.0 CPU |
| `docker-compose.codebox.yml` | CodeBox | `march7_codebox` | 512M memory, 0.5 CPU |
| `docker-compose.bot.yml` | Bot | `march7_bot` | - |

All services communicate over the `march7_net` bridge network.

## Quick Start

### Clean start (first time or after changes)
```bash
cd docker
docker compose down
docker rmi march7_bot:latest 2>/dev/null || true
DOCKER_BUILDKIT=1 docker compose build march7_bot
docker compose up -d
docker compose logs -f march7_bot
```

### From project root
```bash
docker compose -f docker/docker-compose.yml up -d
docker compose -f docker/docker-compose.yml logs -f march7_bot
```

### Individual service operations
```bash
# Start only Redis
docker compose -f docker/docker-compose.redis.yml up -d

# Start only bot (requires Redis + Qdrant + CodeBox running)
docker compose -f docker/docker-compose.bot.yml up -d

# Rebuild only bot (other services unaffected)
DOCKER_BUILDKIT=1 docker compose -f docker/docker-compose.bot.yml build march7_bot
```

## Data Persistence

All data is stored in `docker/volumes/` via bind mounts:

| Directory | Purpose |
|-----------|---------|
| `redis_data/` | Redis append-only file (conversation history, T1 Active Memory) |
| `qdrant_data/` | Qdrant vectors (episodic memories, T2 Wiki Pages) |
| `hf_cache/` | Downloaded HuggingFace embedding models |

## Commands Reference

```bash
# Start all services
docker compose up -d

# Stop all services
docker compose down

# Stop + remove volumes (⚠️ deletes all data)
docker compose down -v

# Rebuild bot image
DOCKER_BUILDKIT=1 docker compose build march7_bot

# View logs
docker compose logs -f march7_bot    # Bot only
docker compose logs -f redis         # Redis only
docker compose logs -f               # All services

# Restart bot
docker compose restart march7_bot

# Exec into bot container
docker exec -it march7_bot bash

# Health check
docker compose ps
```

## Hot-Reload

Code changes in `src/`, `gateway/`, `memories/`, or `config.py` take effect automatically via `watchmedo auto-restart` — no rebuild or container restart needed.

Only rebuild the image when:
- Changing `requirements.txt` (new dependencies)
- Modifying the `Dockerfile` itself

## Environment Variables

The bot service reads from `../.env` plus inline `environment` overrides. Key variables:

```env
# Discord
DISCORD_LLM_BOT_TOKEN=your_bot_token
DISCORD_LLM_BOT_CLIENT_ID=your_client_id

# Gateway
ENTRYPOINT_CMD=gateway
GATEWAY_ENABLED_PLATFORMS=discord
DISCORD_GATEWAY_ENABLED=true

# LLM
TOOL_LLM_ENDPOINT=http://host.docker.internal:1234/v1
TOOL_LLM_MODEL=qwen3-coder-30b-a3b-instruct

# Infrastructure (internal Docker network addresses)
REDIS_URL=redis://redis:6379
QDRANT_URL=http://qdrant:6333
CODEBOX_API_URL=http://codebox:8069
```
