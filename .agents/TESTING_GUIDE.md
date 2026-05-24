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

## Selection Guide

- Overflow, queue, consolidation: `tests/unit/*overflow*`,
  `tests/integration/*consolid*`, `tests/e2e/*consolid*`
- T2 semantic memory & consolidation: `tests/unit/t2_memory_test.py`,
  `tests/unit/t2_consolidation_tool_test.py`
- Gateway or Discord adapter: `tests/gateway/*`
- A2A client/server behavior: tests matching `*a2a*`
