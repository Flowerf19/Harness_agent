# Agent Guidance Index

Repo guidance is intentionally small. Read it before changing runtime behavior;
use CodeGraph for structural code questions and the focused testing guide for
verification commands.

## Read Order

1. [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) — runtime modes, architecture
   boundaries, service ownership, and key environment variables.
2. [AGENT_RULES.md](AGENT_RULES.md) — safety invariants, workflow, style, and
   verified gotchas.
3. [TESTING_GUIDE.md](TESTING_GUIDE.md) — test layout, service dependencies,
   and commands.
4. [../ARCHITECTURE.md](../ARCHITECTURE.md) — the broader trust-boundary and
   System Gateway review when a change crosses services or security domains.

## Structural Lookup

Prefer the repository's CodeGraph index for definitions, callers, callees,
and impact. Use native search/read for literal text, documentation, manifests,
and configuration. The project index is initialized with:

```bash
codegraph init -i
```

## Critical Boundaries

- Production March7 boots with `python -m gateway`. That process owns the
  Discord gateway adapter, March7 agent, and A2A server on port `8000`.
  `python -m twin.march7` is a thinner standalone A2A development entrypoint.
- Evernight runs separately with `python -m twin.evernight` on A2A port `8001`.
  It owns owner chat, consolidation triggers, notifications, and self-heal.
- March7 owns its T1 session state. Evernight must use A2A skills or shipped
  consolidation entries; it must not read or clear March7 T1 Redis keys.
- T1 is agent/scope-local Redis JSON state. T2 is shared Redis Stack timeline
  data on `TIMELINE_REDIS_DB=0`. T3 is Markdown profile data under `memories/`.
  T2 recall is tool-only through `search_memory`; do not add automatic
  preflight retrieval without measured evidence and an explicit design change.
- Gateway platform adapters translate native events into unified models. Core
  routing, agents, memory, tools, and approval logic must not depend on Discord
  SDK objects or labels.
- System Gateway is the only host-operation boundary. Containers use
  `host_system` and HMAC-signed requests. Shell requests require a fresh,
  action-bound, actor-bound, single-use approval token. Do not log secrets or
  bypass the service through Docker, Redis, or direct host execution.
- No working Zalo adapter exists. Keep `zalo` disabled until its adapter and
  configuration contract are implemented.

## Quick Links

- Docker runbook: [../docker/README.md](../docker/README.md)
- LLM and embedding configuration: [../twin/shared/llm/README.md](../twin/shared/llm/README.md)
- System Gateway package and runbook: [../services/system_gateway/README.md](../services/system_gateway/README.md)
- Bootstrap and calibration scripts: [../scripts/README.md](../scripts/README.md)
