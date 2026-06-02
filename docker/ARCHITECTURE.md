# Docker Ownership Map

This Docker setup is split by ownership folders and runtime boundaries.

## Folder Layout

```text
docker/
├── shared/              # shared base image and shared Docker primitives
│   └── Dockerfile.base
│   ├── Dockerfile.bash-executor
│   └── docker-compose.*.yml
├── march7/              # March7-owned image
│   └── Dockerfile
│   └── docker-compose.yml
├── evernight/           # Evernight-owned image
│   └── Dockerfile
│   └── docker-compose.yml
└── docker-compose.yml   # master include file
```

## Shared Infrastructure

These services are shared by both agents:

| Service | Compose file | Owner | Purpose |
| --- | --- | --- | --- |
| `base` | `shared/docker-compose.base.yml` | shared | common Python runtime image |
| `redis` | `shared/docker-compose.redis.yml` | shared | T1 active memory and T2 timeline/vector memory |
| `codebox` | `shared/docker-compose.codebox.yml` | shared | sandboxed Python/code execution |
| `bash-executor` | `shared/docker-compose.bash-executor.yml` | shared privileged tool | host command execution behind approval |
| `march7_net` | `docker-compose.yml` | shared | service discovery network |

## Agent-Owned Services

| Service | Compose file | Owner | Public boundary |
| --- | --- | --- | --- |
| `march7` | `march7/docker-compose.yml` + `march7/Dockerfile` | March7 | A2A `:8000`, Discord main bot |
| `evernight` | `evernight/docker-compose.yml` + `evernight/Dockerfile` | Evernight | A2A `:8001`, Discord DM/tag/`!9` bot |

March7 owns normal chat, tool calling, shared-memory writes, and the A2A memory boundary:

- `get_snapshot`
- `clear_session`

Evernight owns its own Discord interaction surface and background work:

- independent DM/tag/`!9` chat
- notification and approval DMs for work March7 needs to report or request
- inactivity consolidation
- T2 timeline consolidation/search support
- self-heal monitor

Evernight must use March7 A2A for March7 memory. It should not read March7 T1 Redis keys directly.

## Environment Ownership

March7-private:

- `DISCORD_MARCH7_TOKEN`
- `DISCORD_MARCH7_CLIENT_ID`
- `MARCH7_A2A_PORT`
- `MARCH7_REDIS_DB`
- `MARCH7_PERSONA_PATH`

Evernight-private:

- `DISCORD_EVERNIGHT_TOKEN`
- `DISCORD_EVERNIGHT_CLIENT_ID` (reserved)
- `EVERNIGHT_A2A_PORT`
- `EVERNIGHT_REDIS_DB`
- `EVERNIGHT_PERSONA_PATH`
- `SELF_HEAL_*`
- `POLL_INTERVAL`

Shared:

- `REDIS_URL`
- `TIMELINE_REDIS_DB`
- `CODEBOX_API_URL`
- `BASH_EXECUTOR_URL`
- `LLM_*`
- `QWEN_*`
- `EMBEDDING_*`

Peer/coordination:

- `EVERNIGHT_A2A_URL`: March7 -> Evernight
- `MARCH7_URL`: Evernight -> March7
- `MARCH7_REDIS_DB`: March7 T1 active memory DB
- `EVERNIGHT_REDIS_DB`: Evernight T1 active memory DB
- `TIMELINE_REDIS_DB`: shared T2 RediSearch DB; must be `0` for Redis Stack

## Startup

From `docker/`:

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f march7 evernight
```

Expected health endpoints:

- March7: `http://localhost:8000/.well-known/agent.json`
- Evernight: `http://localhost:8001/.well-known/agent.json`
