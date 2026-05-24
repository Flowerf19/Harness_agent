# Agent Guidance Index

Repo guidance is intentionally small. Use it for policy, runtime boundaries, and
verified commands. Use CodeGraph for structural code questions.

## Read Order

1. [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) - runtime, architecture boundaries,
   service ownership, key env vars.
2. [AGENT_RULES.md](AGENT_RULES.md) - safety, workflow, style, PR hygiene,
   verified gotchas.
3. [TESTING_GUIDE.md](TESTING_GUIDE.md) - test layout and verification commands.

## CodeGraph Usage

Prefer CodeGraph over broad file reads for structural questions:

- Definitions/signatures: `codegraph_search` or `codegraph_node`
- Callers/callees/impact: `codegraph_callers`, `codegraph_callees`,
  `codegraph_impact`
- Feature or bug context: `codegraph_context`, then one focused
  `codegraph_explore`
- File tree from the index: `codegraph_files`

Use native search/read for literal text, comments, docs, configs, manifests,
or after CodeGraph has identified the exact file to inspect.

## Specialized Skills

When executing tasks, agents (both parent and subagents) should apply the following specialized skills based on the task type:

- **Planning & Design**: Use the `implementation-planner` skill to analyze specs, features, or bugs and create an execution-ready `implementation_plan.md` before writing code.
- **Coding & Implementation**: Use the `thoughtful-coder` skill for careful, surgical code changes. Optimize for: Correctness -> Minimal diff -> Consistency -> Verifiable outcome -> Simplicity.
- **Project Documentation**: Use the `architecture-docs` skill to create and maintain concise architecture and agent guidance documents in the `.agents/` directory.
- **README Updates**: Use the `create-readme` skill to generate or rewrite high-quality `README.MD` files based on repository evidence.

## Copilot MCP Setup

GitHub Copilot supports MCP tools, but CodeGraph is not built in. If Copilot
does not already expose CodeGraph tools, configure a local MCP server manually
with this command shape:

```json
{
  "mcpServers": {
    "codegraph": {
      "type": "stdio",
      "command": "codegraph",
      "args": ["serve", "--mcp", "--path", "/home/flowerf/Projects/march7"]
    }
  }
}
```

For Copilot custom agents, allow either all tools (`tools: ["*"]`) or the
specific CodeGraph MCP tool names exposed by the client. Without this MCP
server, agents should fall back to targeted search/read.

## Critical Boundaries

- **March7** owns primary public chat, tool calling, its own T1/T3 memory, and reads T2.
- **Evernight** owns consolidation, background jobs, self-heal, and private owner chat (via DM and `!9` prefix) with its own T1/T3 memory.
- Evernight must use A2A to interact with March7 session memory; it must not
  bypass the boundary by reading March7 T1 keys directly.
- Bash Executor is privileged. Keep approval/audit behavior intact and do not
  log secrets.

## Quick Links

- Docker/local runbook: [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md)
- LLM providers: [../README_LLM_PROVIDERS.md](../README_LLM_PROVIDERS.md)
- Bash Executor security: [../README_BASH_EXECUTOR.md](../README_BASH_EXECUTOR.md)
- Docker services: [../docker/README.md](../docker/README.md)
