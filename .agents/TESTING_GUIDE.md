# TESTING_GUIDE

March7 uses `pytest` with unit, integration, e2e, and manual test folders.

## Test Layout

- `tests/unit/`: isolated logic such as queue, t2_memory, A2A, memory, transport.
- `tests/integration/`: flows that may require services such as Redis.
- `tests/e2e/`: full runtime flows such as chat overflow to consolidation.
- `tests/manual/`: scripts for manual verification.

## Common Commands

```bash
pytest tests/unit/ -v
pytest tests/integration/ -v
pytest tests/e2e/ -v
```

Run the smallest relevant command first. Integration and e2e tests usually need
Redis; use Docker Compose from [../docker/README.md](../docker/README.md) when
local services are not already running.

## Recently Verified

Baseline after the unified discussion memory wire-up (2026-05-25):

```bash
python -m compileall twin gateway
pytest tests/unit
docker compose -f docker/docker-compose.yml ps
```

Observed result: `pytest tests/unit` reports `66 passed`. Docker Compose
should show `march7`, `evernight`, `redis`, `codebox`, and `bash-executor`
healthy after a fresh `up -d --build`.

The legacy `tests/integration/overflow_trigger_test.py` was removed when
`TOKEN_LIMIT_REACHED` was retired. Equivalent coverage now lives in
`tests/unit/summary_policy_test.py` and `tests/unit/discussion_consolidator_test.py`.

## Selection Guide

- Summary policy triggers (token / message_count / idle, locking):
  `tests/unit/summary_policy_test.py`
- DiscussionConsolidator (single-user, channel fan-out, JSON hardening, merge):
  `tests/unit/discussion_consolidator_test.py`
- InactivityTrigger (scope iteration, evaluate dispatch, error tolerance):
  `tests/unit/inactivity_trigger_test.py`
- Unified discussion memory baseline: `tests/unit/t1_redis_stack_storage_test.py`,
  `tests/unit/t1_context_builder_test.py`, `tests/unit/t2_memory_test.py`,
  `tests/unit/consolidation_runner_test.py`.
- T2 semantic memory & consolidation: `tests/unit/t2_memory_test.py`,
  `tests/unit/t2_consolidation_tool_test.py`
- Gateway or Discord adapter: `tests/gateway/*`
- A2A client/server behavior: tests matching `*a2a*`
