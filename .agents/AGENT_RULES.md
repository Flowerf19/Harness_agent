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
- **NEVER use `view_file` or `grep`** to read code files for exploration if `codegraph` tools (like `codegraph_explore` or `codegraph_node`) have already retrieved the symbol/source code. Native read/search must only be used to confirm specific details not covered by CodeGraph or to inspect configuration/docs/manifests.
- **Invoke skills properly** by setting `IsSkillFile: true` in the `view_file` call when reading a skill's `SKILL.md`.
- **Enforce the planning workflow:** Write planning artifacts (`implementation_plan.md`) to `<appDataDir>/brain/<conversation-id>/implementation_plan.md` first, set `RequestFeedback: true` in metadata, and wait for user approval before making any code changes.
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

- T3 storage is Markdown via `MarkdownStorage`, not YAML.
- `README.MD` is the project README filename currently used at repo root.
- Root lint/format/type-check config is not currently established; do not add
  or run repo-wide formatters as part of unrelated work.
- The repository `.gitignore` allows source under `twin/**/memories/` (added
  explicit `!twin/**/memories/**` exception). New source files there are
  tracked normally. `__pycache__` under those paths is re-ignored.
- Unified discussion memory intentionally keeps T2 user-centric. Do not store
  channel sentinel ids in `T2Page.user_id`; put channel metadata in
  `source_refs`. `T2Page.participants` is TAG-indexed in the FT schema for
  future joint `(user, channel)` filters.
- The legacy `TOKEN_LIMIT_REACHED` event was removed. Summary flow is
  `SUMMARY_REQUESTED` → Evernight A2A `consolidate_discussion` →
  `SUMMARY_COMPLETED`/`SUMMARY_FAILED` → T1 cleanup. Do not reintroduce the
  old overflow_queue path on the trigger side.
- Each agent runs its own `InactivityTrigger` in-process against its own
  `SummaryStateRepository` (March7 scans `user` + `channel`; Evernight scans
  `user` only). The trigger drives `SummaryPolicy.evaluate` directly — do not
  call `ConsolidationRunner` from the trigger path.
- **Docker entry for March7 is `python -m gateway`** (`gateway/__main__.py`),
  not `python -m twin.march7`. When wiring new background tasks (triggers,
  workers, schedulers) for March7, add them to `gateway/__main__.py` so they
  run inside the container. `twin/march7/__main__.py` is a thinner local-dev
  entry — keep it in sync but treat the gateway entry as authoritative.
- Local Redis/T2 data may be disposable during development because T3 Markdown
  is the durable profile/core memory. Confirm before deleting production data.
- After modifying the T2 FT schema, the existing index must be dropped and
  recreated (`FT.DROPINDEX idx:t2:page` then restart). `_create_index` skips
  creation if the index already exists.
