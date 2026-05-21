# Copilot Instructions for March7

Use this file as the repo entrypoint. Keep context small and load deeper docs
only when the task requires them.

## Start Here

- Read [`.agents/README.md`](../.agents/README.md) for the current guidance
  index and CodeGraph policy.
- Read [`.agents/PROJECT_CONTEXT.md`](../.agents/PROJECT_CONTEXT.md) before
  changing runtime, architecture boundaries, env vars, Docker, or memory flows.
- Read [`.agents/AGENT_RULES.md`](../.agents/AGENT_RULES.md) before editing
  code.
- Read [`.agents/TESTING_GUIDE.md`](../.agents/TESTING_GUIDE.md) before
  verification.

Do not read every `.agents/*` file by default. Read `plans/` only when the user
asks about a specific plan or the current task references one.

## CodeGraph Policy

If a CodeGraph MCP/tool is available, prefer it for structural questions:

- symbol definitions and signatures
- callers, callees, dependency impact
- architecture or feature context across source files
- indexed file structure

Use normal search/read for literal text, docs, manifests, configs, tests, and
files already identified by CodeGraph.

## Hard Boundaries

- March7 owns chat, tool calling, T1 active memory, and T3 profile memory.
- Evernight owns consolidation, background jobs, and self-heal flows.
- Evernight must interact with March7 T1 through A2A, not direct Redis key
  access.
- Bash Executor is privileged. Preserve approval/audit behavior and never log
  secrets.
