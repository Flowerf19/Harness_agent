# PROJECT_CONTEXT

Runtime and architecture context for March7. Keep this file focused on facts
agents must know before changing behavior; use CodeGraph for source structure.

## Runtime Modes

### Docker Compose (primary)

Use [../docker/docker-compose.yml](../docker/docker-compose.yml) and
[../docker/README.md](../docker/README.md) for the full system.

Main services:

- `redis`: Redis Stack for T1 coordination/storage and T2 semantic memory.
- `codebox`: sandboxed Python execution service.
- `bash-executor`: privileged host command execution with approval/audit.
- `march7`: Gateway, Discord bot, and March7 A2A server.
- `evernight`: Evernight bot, consolidation, and self-heal worker.

Expected local endpoints:

- March7 A2A: `http://localhost:8000/.well-known/agent.json`
- Evernight A2A: `http://localhost:8001/.well-known/agent.json`
- Codebox: port `8069`
- Bash Executor: port `8374`

### Local Python (secondary)

```bash
pip install -r requirements.txt
python -m gateway
python -m twin.march7
python -m twin.evernight
```

Integration and e2e flows usually still need Redis, preferably provisioned by
Docker.

## Architecture Boundaries

- `gateway/`: platform adapters and routing, currently focused on Discord.
- `twin/march7/`: conversational agent, chat/tool loop, T1 active memory, T3
  profile memory, A2A server on default port `8000`.
- `twin/evernight/`: background consolidation and self-heal agent, A2A server
  on default port `8001`.
- `twin/shared/`: shared A2A, LLM, tool, memory, and transport code.

Evernight must access March7 session state through A2A skills such as
`get_snapshot` and `clear_session`; do not couple it directly to March7 Redis
keys unless the architecture explicitly changes.

## Memory Tiers

- **T1 Active Memory**: short-term session context in Redis. `legacy`
  Redis/HASH is the stable path; `redis_stack` remains a cutover/experimental
  phase unless tests prove parity.
- **T2 Episodic/Wiki Memory**: Redis Stack semantic/vector memory.
- **T3 Core/Profile Memory**: Markdown files via `MarkdownStorage`, default
  base path `memories/`.

## Key Environment Groups

Shared infrastructure and LLM:

- `REDIS_URL`
- `CODEBOX_API_URL`
- `BASH_EXECUTOR_URL`
- `T1_STORAGE_PHASE`
- `T1_CONTEXT_MAX_TOKENS`
- `T1_CONTEXT_MAX_MESSAGES`
- `LLM_PROVIDER` and provider-specific chat/embedding variables

March7:

- `MARCH7_A2A_PORT` default `8000`
- `MARCH7_REDIS_DB` default `0`
- `MARCH7_PERSONA_PATH` default `twin/march7/personas`

Evernight:

- `EVERNIGHT_A2A_PORT` default `8001`
- `EVERNIGHT_REDIS_DB` default `1`
- `EVERNIGHT_PERSONA_PATH` default `twin/evernight/personas`
- `MARCH7_URL` default `http://march7:8000`
- `INACTIVITY_SECONDS` default `1800`
- `POLL_INTERVAL` default `60`
- `SELF_HEAL_ENABLED` default `true`

Discord/Gateway:

- `GATEWAY_ENABLED_PLATFORMS` default `discord`
- `DISCORD_GATEWAY_ENABLED` default `true`
- `DISCORD_MARCH7_TOKEN`
- `DISCORD_EVERNIGHT_TOKEN`

Do not print `.env` files or token values.
