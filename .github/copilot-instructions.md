# Copilot instructions (March7)

Use these repo-specific guidelines when editing code in this workspace.

## Read-first docs

- High-level architecture: [`.github/ARCHITECTURE.md`](../.github/ARCHITECTURE.md)
- Agent rules / boundaries: [`.github/AGENT_RULES.md`](../.github/AGENT_RULES.md)
- How to run: [`.github/PROJECT_CONTEXT.md`](../.github/PROJECT_CONTEXT.md)
- Task workflow: [`.github/TASK_WORKFLOW.md`](../.github/TASK_WORKFLOW.md)
- Testing guide: [`.github/TESTING_GUIDE.md`](../.github/TESTING_GUIDE.md)
- LLM & embeddings config: [`README_LLM_PROVIDERS.md`](../README_LLM_PROVIDERS.md)

## Architecture constraints

- Twin agents: **March7** (chat) and **Evernight** (background) communicate via A2A boundary.
- Memory tiers:
  - T1 Active Memory: Redis
  - T2 Episodic/Wiki: Qdrant
  - T3 Core/Profile: Markdown files

## LLM services (keep it lean)

- Only 2 LLM protocols are supported:
  - `gemini` → `GeminiService`
  - `openai_compat` (OpenAI-compatible `/chat/completions`) → `OpenAIService`
- Embeddings use OpenAI-compatible `/embeddings` via `OpenAIEmbeddingService`.

## Operational notes

- Prefer Docker Compose for running the system (`docker/docker-compose.yml`).
- Do not introduce new provider-specific LLM services unless explicitly requested.

## Docs update requirement

- After completing a change (feature/refactor/behavior change), update docs as needed:
  - Project-level README: [`README.MD`](../README.MD)
  - Relevant project docs (e.g. provider/config docs): [`README_LLM_PROVIDERS.md`](../README_LLM_PROVIDERS.md)
  - Copilot instructions: [`.github/copilot-instructions.md`](../.github/copilot-instructions.md)
