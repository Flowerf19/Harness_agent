# Agent Docs Index

## Thứ tự đọc khuyến nghị

1. [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md)
2. [ARCHITECTURE.md](ARCHITECTURE.md)
3. [AGENT_RULES.md](AGENT_RULES.md)
4. [TASK_WORKFLOW.md](TASK_WORKFLOW.md)
5. [CODING_STYLE.md](CODING_STYLE.md)
6. [TESTING_GUIDE.md](TESTING_GUIDE.md)
7. [GIT_WORKFLOW.md](GIT_WORKFLOW.md)
8. [KNOWLEDGE_BASE.md](KNOWLEDGE_BASE.md)

## Boundary quan trọng

- **March7** xử lý chat chính, tool calling, T1/T3.
- **Evernight** xử lý consolidation, background jobs, self-heal.
- Evernight phải dùng A2A để lấy/clear T1 của March7.
- Một Redis Stack service có thể phục vụ cả T1 và T2.
- T1 hiện ưu tiên Redis basic/HASH path ổn định (`legacy`).
- T2 dùng Redis Stack features cho semantic/vector memory.
- Bash Executor là tool đặc quyền, luôn cần approval/audit.

## T1 Storage Phase

| Phase | Mô tả | Trạng thái |
|-------|-------|------------|
| `legacy` | Redis basic/HASH | Stable, path chính |
| `redis_stack` | Redis Stack JSON/Search | Experimental, cutover sau parity test |

## Quick links

- [Cách chạy Docker/local](../docker/README.md)
- [LLM providers config](../README_LLM_PROVIDERS.md)
- [Bash Executor security](../README_BASH_EXECUTOR.md)