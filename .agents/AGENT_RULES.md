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
