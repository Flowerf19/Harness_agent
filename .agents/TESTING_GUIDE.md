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

Baseline after the memory rewrite wire-up (2026-05-28):

```bash
python -m py_compile twin/march7/container.py twin/evernight/container.py twin/shared/config/settings.py
pytest
docker compose -f docker/docker-compose.yml ps
```

Observed result: `pytest` reports `221 passed, 13 skipped`. Docker Compose
should show `march7`, `evernight`, `march7-redis`, `march7-codebox`, and
`march7-bash-executor` healthy after a fresh `up -d --build`.

The legacy overflow/discussion-consolidator tests were removed with the old
memory stack. Equivalent coverage now lives under `tests/unit/memory/`.

## Selection Guide

- Active memory + summary triggers:
  `tests/unit/memory/active_test.py`, `tests/unit/memory/manager_test.py`
- InactivityTrigger (scope iteration, evaluate dispatch, error tolerance):
  `tests/unit/inactivity_trigger_test.py`
- T2 timeline/search/topic/cleanup/consolidation:
  `tests/unit/memory/timeline_store_test.py`, `tests/unit/memory/search_test.py`,
  `tests/unit/memory/topic_resolver_test.py`,
  `tests/unit/memory/consolidator_test.py`, `tests/unit/memory/cleanup_test.py`
- T3 profile/tooling:
  `tests/unit/memory/profile_test.py`, `tests/unit/memory/tools_test.py`
- Gateway or Discord adapter: `tests/gateway/*`
- A2A client/server behavior: tests matching `*a2a*`
