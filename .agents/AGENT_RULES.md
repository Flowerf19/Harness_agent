# AGENT_RULES

Rules for coding agents working in this repository.

## Safety

- Do not reveal secrets. Never print full `.env` files, Discord tokens, API
  keys, or URLs containing credentials.
- Bash Executor is privileged. Preserve user approval, auditability, timeouts,
  and security checks. Avoid destructive host commands unless explicitly
  requested.
- Keep the March7/Evernight A2A boundary intact. Evernight must not read or
  clear March7 T1 state by direct Redis key access.

## Working Style

- **Use CodeGraph first** for structural questions (definitions, signatures, callers, callees, impact, and feature context).
- **NEVER re-read code files** with native read/grep for exploration once `codegraph` tools (`codegraph_explore`, `codegraph_node`) have already returned the symbol/source. Native read/search is only for confirming specifics CodeGraph didn't cover, or for inspecting config/docs/manifests.
- **Plan before coding.** For any non-trivial feature/bug, produce a plan (via the `implementation-planner` skill) and get user approval before editing code. The plan is part of the conversation — do not write it into an external app-data directory.
- Make small, task-scoped changes. Avoid broad refactors, speculative abstractions, unrelated formatting, and new tooling unless requested.
- If a change affects runtime flow, env vars, Docker, memory schema, or public
  behavior, update relevant docs in this folder and project READMEs.

## Skills

Curated skills live globally at `~/.claude/skills/` (clone of [Flowerf19/agents-skills](https://github.com/Flowerf19/agents-skills)) — applies to all agents in every project, not just this repo.

- **Claude Code** auto-discovers them at `~/.claude/skills/`. Invoke with `/<skill-name>` or via the Skill tool.
- **Other agents** (Antigravity, Gemini, Cursor, generic LLMs): point them at `~/.claude/skills/<name>/SKILL.md`.

Available: `implementation-planner` (plan before code), `thoughtful-coder` (surgical changes), `debug-investigator` (root cause before any fix), `code-reviewer` (independent review before merge), `architecture-docs` (refresh `.agents/`), `create-readme` (root README from evidence).

Update upstream: `cd ~/.claude/skills && git pull`.

## Python Conventions

- Prefer clear async I/O with explicit timeouts for HTTP, Discord, Redis, and
  LLM calls.
- Handle cancellation and clean shutdown for background tasks.
- Use type hints on public functions and methods. Prefer `str | None` over
  `Optional[str]` for new Python 3.10+ code.
- Log enough context to debug, but never log secrets.
- Add retry/backoff only for concrete transient failure modes.

## Verification And PR Hygiene

- Choose focused tests from [TESTING_GUIDE.md](TESTING_GUIDE.md).
- For external I/O changes, verify timeout/error paths where practical.
- PR summaries should include context, change list, and exact verification.
- Commit messages should be short and specific, preferably
  `type(scope): message`.

## Verified Gotchas

- T3 storage is Markdown via `MarkdownProfileStore`, not YAML.
- `README.md` is the project README filename currently used at repo root.
- Root lint/format/type-check config is not currently established; do not add
  or run repo-wide formatters as part of unrelated work.
- Memory source lives under `twin/shared/memory/`. Do not recreate
  `twin/march7/memories/`, `twin/evernight/memories/`, or
  `twin/shared/memories/`.
- T2 timeline intentionally keeps memories user-centric. Channel scope is
  consolidated by fan-out per participant; do not store channel sentinel ids
  as `T2Memory.user_id`.
- The legacy `TOKEN_LIMIT_REACHED`, `DiscussionConsolidator`, and
  `consolidate_t2_memory` paths were removed. Current flow is
  `ActiveMemory` threshold/idle → `SharedMemoryManager.consolidate_scope` →
  `Consolidator` → `CleanupScheduler`.
- Each agent builds the same shared stack (`ActiveMemory`,
  `MarkdownProfileStore`, `TimelineStore/Search`, `Consolidator`, `Cleanup`)
  in its container. T2 RediSearch indexes must use Redis DB 0
  (`TIMELINE_REDIS_DB=0`).
- **`twin/shared/tools/` consolidated 2026-05-26.** Core types live in `twin.shared.tools.registry`; individual tool classes live under `twin.shared.tools.modules.<domain>.<tool>` (domains: `execution`, `memory`, `profile`, `web`). The paths `twin.shared.tools.base_tool` / `tool_registry` / `tool_discovery` / `implementations.system.*` no longer exist — do not recreate them.
- **LLM/embedding endpoints chạy trên host phải dùng `host.docker.internal`, không phải `localhost`.** Container march7/evernight có `extra_hosts: host.docker.internal:host-gateway` trong compose; `localhost` trong `.env` sẽ trỏ vào chính container và fail với `Cannot connect to host localhost:<port>`. Áp dụng cho `OPENAI_API_URL`, `EMBEDDING_API_URL`, `LM_STUDIO_API_URL`, `TOOL_LLM_ENDPOINT`. Service nội-mạng Docker (redis, codebox, bash-executor, evernight) thì dùng service name.
- **Docker entry for March7 is `python -m gateway`** (`gateway/__main__.py`),
  not `python -m twin.march7`. When wiring new background tasks (triggers,
  workers, schedulers) for March7, add them to `gateway/__main__.py` so they
  run inside the container. `twin/march7/__main__.py` is a thinner local-dev
  entry — keep it in sync but treat the gateway entry as authoritative.
- Local Redis/T2 data may be disposable during development because T3 Markdown
  is the durable profile/core memory. Confirm before deleting production data.
- After modifying the T2 FT schema, the existing indexes must be dropped and
  recreated (`FT.DROPINDEX idx:t2:mem`, `FT.DROPINDEX idx:t2:topic`, then
  restart). `_create_*_index` skips creation if the index already exists.
