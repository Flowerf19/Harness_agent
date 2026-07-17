# TESTING_GUIDE

March7 uses `pytest`. `pytest.ini` sets `tests/` as the root, discovers both
`*_test.py` and `test_*.py`, and enables `pytest-asyncio` auto mode.

## Test Layout

- `tests/unit/` — isolated agent, memory, gateway, transport, tool, and
  System Gateway client logic; most tests use mocks and need no service.
- `tests/gateway/` — unified gateway models, core routing, and adapter-facing
  behavior.
- `tests/services/external/` — external service clients such as Codebox.
- `tests/services/tools/` — tool wrappers, including the Tavily MCP-backed
  `web_search` wrapper.
- `services/system_gateway/tests/` — native host service configuration,
  capabilities, and HTTP server tests. This directory is outside the root
  `pytest.ini` test path and must be named explicitly.
- `tests/integration/`, `tests/e2e/`, and `tests/manual/` currently contain
  scaffolding; `tests/e2e/` also contains reports and saved verification
  evidence rather than an automated suite.

## Commands

Use the interpreter that has the project dependencies installed:

```bash
python -m pytest tests/unit -q
python -m pytest tests/unit/memory -q
python -m pytest tests/gateway -q
python -m pytest services/system_gateway/tests -q -p no:phoenix
python -m pytest tests -q \
  --ignore=tests/unit/discord_send_response_test.py \
  --ignore=tests/unit/evernight_discord_adapter_test.py \
  --ignore=tests/unit/system_gateway_cli_test.py \
  -p no:phoenix
```

When the `discord_bot` Conda environment exists, the equivalent form is
`conda run -n discord_bot python -m pytest ...`. Do not use bare `pytest`, and
do not assume that the Conda environment exists on every host.

## Service Dependencies

- Unit tests normally need no Redis, LLM, Discord, or Codebox service because
  external calls are mocked.
- `tests/services/external/*_integration_test.py` may call a real network
  endpoint; run those only when the endpoint is configured.
- Integration or live memory checks need Redis Stack. Docker Compose provisions
  it; see [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md).
- Tests importing Discord adapters need the `discord.py` dependency. The full
  baseline command above excludes the known Discord-dependent files and
  disables the `phoenix` plugin to avoid collection conflicts.

## Focused Selection

- T1 active memory and consolidation: `tests/unit/memory/active_test.py`,
  `tests/unit/memory/manager_consolidation_test.py`, and
  `tests/unit/memory/consolidate_tool_test.py`.
- T2 timeline/vector retrieval: `tests/unit/memory/test_store_schema.py`,
  `tests/unit/memory/tools_test.py`, `tests/unit/memory/test_rrf.py`, and
  `tests/unit/memory/test_embedding_prefix.py`.
- T3 profile updates: `tests/unit/memory/profile_test.py` and
  `tests/unit/manage_profile_tool_test.py`.
- Gateway and A2A: `tests/gateway/` plus
  `tests/unit/a2a_client_test.py` and
  `tests/unit/march7_handle_chat_scope_test.py`.
- Native System Gateway: `services/system_gateway/tests/` plus
  `tests/unit/system_gateway_*_test.py`.

## Verification Baseline

Verified during this documentation refresh with Python 3.14.6:

```text
487 passed, 6 skipped
```

Command: the full-suite command shown above, from the repository root. Live
Discord, Redis, LLM, Codebox, and host-gateway smoke tests remain environment-
dependent and are not represented by this baseline.
