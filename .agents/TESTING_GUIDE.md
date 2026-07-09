# TESTING_GUIDE

March7 dùng `pytest`. Test layout phản ánh ranh giới runtime: memory stack, gateway,
transport, và external services. Dùng file này để chọn test focused; dùng CodeGraph
để tìm symbol cụ thể bên trong mỗi test.

## Test Layout

- `tests/unit/` — logic cô lập, không cần service ngoài:
  - `tests/unit/memory/` — memory stack: `active_test.py`,
    `manager_consolidation_test.py`, `consolidate_tool_test.py`,
    `profile_test.py`, `test_store_schema.py`, `tools_test.py`, `test_rrf.py`,
    `test_embedding_prefix.py`.
  - `tests/unit/` (gốc) — `inactivity_trigger`, `a2a_client`, `http_transport`,
    `tool_bootstrap`, `march7_handle_chat_scope`, `discord_send_response`.
- `tests/gateway/` — gateway core/adapter + models (`test_gateway`,
  `test_core_handler`, `test_models`).
- `tests/services/external/` — external I/O clients such as `codebox_client`;
  networked web search now goes through the Tavily MCP-backed tool wrapper.
- `tests/services/tools/` — tool wrappers (`code_interpreter_tool`,
  `tavily_search_tool`).
- `tests/services/memories/` — context-level memory (`channel_context`).
- `tests/integration/`, `tests/e2e/`, `tests/manual/` — hiện chỉ còn scaffolding
  (`__init__.py`). Đặt flow cần Redis (integration), full-runtime overflow→
  consolidation (e2e), và script verify tay (manual) vào đây khi viết mới.

## Common Commands

Use the conda env interpreter when available:

```bash
conda run -n discord_bot python -m pytest tests/unit -q
conda run -n discord_bot python -m pytest tests/unit/memory -q
conda run -n discord_bot python -m pytest tests/gateway -q
conda run -n discord_bot python -m pytest tests/services -q
conda run -n discord_bot python -m pytest tests -q
```

Avoid `conda run -n discord_bot pytest ...`; it may resolve to a different
pytest executable than the env's Python. If not using conda, `python -m pytest`
is still preferred over bare `pytest`.

`pytest.ini` discovers both legacy `*_test.py` files and gateway-style
`test_*.py` files.

Full suite với workaround phoenix/strawberry import conflict và bỏ qua các test
cần `discord.py`/gateway CLI:

```bash
conda run -n discord_bot python -m pytest tests -q \
  --ignore=tests/unit/discord_send_response_test.py \
  --ignore=tests/unit/evernight_discord_adapter_test.py \
  --ignore=tests/services/system_gateway_cli_test.py \
  -p no:phoenix
```

## Service Dependencies

- `tests/unit/*` chạy không cần service ngoài (mock Redis/LLM).
- `tests/services/external/*_integration_test.py` gọi network thật (ví dụ
  codebox) — bỏ qua nếu không có endpoint.
- Flow integration/e2e cần Redis, ưu tiên provision qua Docker
  (xem [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md)).
- Cần `discord.py` cài đặt để collect `tests/unit/discord_send_response_test.py`
  và các test import `gateway.adapters.discord`.

## Selection Guide

- T1 active memory / archive / trim → `tests/unit/memory/active_test.py` +
  `manager_consolidation_test.py`
- Cross-DB consolidation / A2A shipped entries →
  `tests/unit/memory/consolidate_tool_test.py` + `manager_consolidation_test.py`
- `InactivityTrigger` → `tests/unit/inactivity_trigger_test.py`
- T2 timeline/vector → `tests/unit/memory/test_store_schema.py`,
  `tools_test.py`, `test_rrf.py`, `test_embedding_prefix.py`
- T3 profile → `tests/unit/memory/profile_test.py` + `tests/unit/manage_profile_tool_test.py`
- March7 chat scope / A2A → `tests/unit/march7_handle_chat_scope_test.py`, `a2a_client_test.py`
- Gateway / Discord → `tests/gateway -q`,
  `tests/unit/discord_send_response_test.py`
- External services (codebox) → `tests/services/external/*`
- Tavily web search MCP wrapper → `tests/services/tools/tavily_search_tool_test.py`
- Tool wrappers → `tests/services/tools/*`

## Last Verified

- 2026-07-03: `conda run -n discord_bot python -m pytest tests -q --ignore=tests/unit/discord_send_response_test.py --ignore=tests/unit/evernight_discord_adapter_test.py --ignore=tests/services/system_gateway_cli_test.py -p no:phoenix`
  → 479 passed, 6 skipped.
- 2026-07-03: Unit memory subset → 399 passed (T2 diary/retrieval + T1
  archive/trim + cross-DB consolidation).
- 2026-07-03: Live probes: T2 recall end-to-end PASS (KNN_RESULT cos 0.499),
  cross-DB consolidation "Cách B" E2E PASS, FT.ALTER thêm `day`/`period_start`/
  `period_end` vào index v2 thành công không cần reindex.
- 2026-06-12: `conda run -n discord_bot python -m pytest tests/unit/manage_profile_tool_test.py -q`
  → passed.

## Historical snapshots (pre-T2-diary; kept for archaeology)

- 2026-06-07: `conda run -n discord_bot python -m pytest tests/unit/approval_gate_test.py tests/gateway tests/unit/evernight_discord_adapter_test.py tests/unit/march7_handle_chat_scope_test.py tests/unit/evernight_agent_test.py tests/unit/discord_send_response_test.py tests/unit/tool_bootstrap_test.py tests/unit/memory/manager_test.py -q`
  → 55 passed.
- 2026-06-07: Docker rebuild/restart via `docker compose -f docker/docker-compose.yml up -d --build`;
  `march7`, `evernight`, the then-current host executor, `codebox`, and `redis` healthy. Evernight
  A2A chat smoke and Chrome snapshot of Evernight's agent card passed while
  A2A was host-published at the time; current compose keeps A2A ports internal.
- 2026-06-07: `conda run -n discord_bot python -m pytest tests/gateway/test_gateway.py tests/gateway/test_models.py tests/gateway/test_core_handler.py tests/unit/march7_handle_chat_scope_test.py tests/unit/evernight_agent_test.py tests/unit/discord_send_response_test.py tests/unit/memory/manager_test.py -q`
  → 44 passed.
- 2026-06-07: `conda run -n discord_bot python -m pytest tests/gateway -q`
  → 22 passed.
- 2026-05-28: `pytest` → 221 passed, 13 skipped; `docker compose ps` healthy cho
  march7/evernight/redis/codebox plus the then-current host executor.
- Lưu ý (2026-06-02): chạy lại đầy đủ cần `discord.py` + Redis trong môi trường;
  thiếu deps sẽ fail ở collection (`ModuleNotFoundError: discord`).
