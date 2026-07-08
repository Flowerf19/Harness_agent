---
status: in-progress
created: 2026-07-07
last_updated: 2026-07-07
---

# Remove System Gateway Legacy Bash Executor

## Summary

Remove the deprecated bash-executor host bridge from System Gateway runtime,
Docker compose, tool registration, tests, and docs. The native System Gateway is
the only host boundary. When the gateway is missing, Evernight should return an
owner-facing install hint instead of executing a bootstrap command through the
old privileged container.

Success criteria:

- No bash-executor service is included by the default Docker stack.
- No model-facing or hidden `execute_host_bash` tool is registered.
- `gateway_admin install` no longer calls a legacy executor.
- Self-heal uses System Gateway when available or direct local Docker command
  outside containers, with no bash-executor fallback.
- Focused unit tests pass and stale docs no longer describe bash-executor as an
  available path.

## Tasks

### GOAL-001: Remove runtime legacy paths

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-001 | Remove bash-executor env/config injection from tool bootstrap and Docker compose. | | |
| TASK-002 | Remove `execute_host_bash` registration and implementation references. | | |
| TASK-003 | Remove legacy bootstrap bridge from `gateway_admin install` and installer exports. | | |
| TASK-004 | Remove bash-executor self-heal fallback and unavailable-handler UI paths. | | |

### GOAL-002: Remove legacy artifacts and tests

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-005 | Delete bash-executor Docker/service/script files. | | |
| TASK-006 | Update focused tests to assert the new no-legacy behavior. | | |
| TASK-007 | Refresh README and architecture docs for the System Gateway-only path. | | |

### GOAL-003: Verify

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-008 | Run focused unit tests for gateway admin, bootstrap, self-heal, System Gateway, and gateway handlers. | | |
| TASK-009 | Run compose config validation and grep for stale legacy references. | | |

## Test Plan

- `python -m pytest tests/unit/gateway_admin_tool_test.py tests/unit/evernight_host_gateway_installer_test.py tests/unit/tool_bootstrap_test.py tests/unit/self_heal_monitor_test.py tests/unit/system_gateway_server_test.py tests/unit/system_gateway_client_test.py -q -p no:phoenix`
- `python -m pytest services/system_gateway/tests -q -p no:phoenix`
- `docker compose -f docker/docker-compose.yml config march7`
- `docker compose -f docker/docker-compose.yml config evernight`
- `rg -n "bash-executor|BASH_EXECUTOR|execute_host_bash|LegacyBashExecutor|/actions/run|8765"`

## Assumptions

- Removing bash-executor means first install cannot be performed by a missing
  gateway from inside Docker; Evernight will provide the exact owner command
  instead.
- Existing native gateway installation remains managed by `system-gateway`
  itself and `/self/update` after it is reachable.
