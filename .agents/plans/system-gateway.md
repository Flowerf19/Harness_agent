---
status: in-progress
created: 2026-06-23
last_updated: 2026-06-23
---

# System Gateway

## Summary

Replace the demo-only `execute_host_bash` host bridge with a proper
cross-platform **System Gateway** subsystem.

The core design is:

```text
March7 / Evernight containers
  -> twin.shared.system_gateway.HostGatewayClient
  -> native system-gateway service on the real host OS
  -> OS adapter: Linux / macOS / Windows
```

Ownership:

- March7 uses the model-facing `host_system` tool for user-requested host
  interactions.
- Evernight owns owner approval, monitoring, install/update orchestration, and
  self-heal integration.
- `system-gateway` runs native on the host and enforces host-local policy,
  authentication, audit, timeouts, and OS-specific execution.

The current Docker `bash-executor` remains as a legacy compatibility path only
while the new client/tool contract lands. It must not be treated as a portable
or secure long-term host gateway.

Success criteria:

- The model-facing tool no longer exposes a Linux-only `execute_host_bash`
  abstraction as the primary host interaction contract.
- March7 and Evernight share one `twin.shared.system_gateway` client/protocol.
- The native gateway reports capabilities before execution, including platform,
  shell, and feature support.
- Linux/macOS/Windows compatibility is handled by host-side adapters, not by
  Docker `nsenter`.
- Owner-approved install/update flow is designed separately from normal tool
  execution.
- Dangerous operations have layered enforcement: owner approval, authenticated
  gateway requests, local policy, audit logs, timeouts, and output bounds.

## Directory Architecture

Shared agent-side protocol/client:

```text
twin/shared/system_gateway/
  __init__.py
  client.py
  types.py
  errors.py
  capabilities.py
  auth.py
  policy.py
  audit.py
```

Model-facing tool:

```text
twin/shared/tools/modules/system/
  __init__.py
  host_system_tool.py

twin/shared/tools/prompts/guides/host_system.md
```

Native host service:

```text
services/system_gateway/
  README.md
  pyproject.toml
  __init__.py
  __main__.py
  server.py
  config.py
  auth.py
  policy.py
  audit.py
  capabilities.py
  adapters/
    __init__.py
    base.py
    linux.py
    macos.py
    windows.py
  actions/
    __init__.py
    docker.py
    services.py
    logs.py
    shell.py
  cli/
    __init__.py
    main.py
  packaging/
    linux/
      system-gateway.service
    macos/
      com.twin.system-gateway.plist
    windows/
      README.md
```

Evernight monitor/orchestrator:

```text
twin/evernight/system_gateway/
  __init__.py
  monitor.py
  installer.py
```

Legacy compatibility:

```text
scripts/bash_executor_standalone.py
scripts/bash_executor_starter.py
docker/shared/Dockerfile.bash-executor
docker/shared/docker-compose.bash-executor.yml
```

## Tasks

### GOAL-001: Lock The Tool Boundary

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-001 | Add `twin/shared/system_gateway/` package with typed request/response/capability/error models only; no runtime execution yet. | ✅ | 2026-06-23 |
| TASK-002 | Add `HostGatewayClient` with `health()`, `capabilities()`, and placeholder `run_action()` / `run_shell()` methods using explicit HTTP timeouts and bounded response handling. | ✅ | 2026-06-23 |
| TASK-003 | Add model-facing `host_system` tool under `twin/shared/tools/modules/system/host_system_tool.py` that depends on `HostGatewayClient` and `ApprovalGate`. | ✅ | 2026-06-23 |
| TASK-004 | Add `host_system.md` guide that describes host interaction as capability-based, not Linux bash. It must tell the model to prefer structured actions and use raw shell only when explicitly requested. | ✅ | 2026-06-23 |
| TASK-005 | Register `host_system` in `SYSTEM_TOOL_SPECS` while keeping `execute_host_bash` temporarily available as legacy, hidden or deprioritized according to implementation constraints. | ✅ | 2026-06-23 |
| TASK-006 | Add tests proving `host_system` rejects missing gateway/capability states cleanly and does not execute anything without approval. | ✅ | 2026-06-23 |

### GOAL-002: Preserve Runtime While Deprecating Bash Executor

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-007 | Add a legacy adapter in `HostGatewayClient` or a narrow compatibility wrapper that can call existing `BASH_EXECUTOR_URL` for Linux demo commands during migration. | | |
| TASK-008 | Mark `scripts/bash_executor_*` and Docker bash-executor docs as legacy Linux-only compatibility, not the System Gateway design. | | |
| TASK-009 | Update README/.agents docs to describe System Gateway as the future host boundary and call out that Docker `nsenter` is Linux-only. | | |
| TASK-010 | Ensure Docker compose can keep current `bash-executor` running until System Gateway native service is implemented; do not remove working demo infrastructure in this phase. | | |

### GOAL-003: Define Gateway Protocol And Policy

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-011 | Define `/health` response with service version, status, uptime, and platform. | | |
| TASK-012 | Define `/capabilities` response with `platform`, `shells`, `features`, `raw_shell`, `structured_actions`, and unsupported feature notes. | | |
| TASK-013 | Define structured action request/response schemas for initial safe actions: system status, disk usage, list Docker containers, container logs, service status. | | |
| TASK-014 | Define raw shell request/response schema separately from structured actions, including shell kind, cwd, timeout, max output, and approval id. | | |
| TASK-015 | Define local policy model: deny by default, allow structured read-only actions by capability, require explicit owner approval for mutating actions, and require separate raw-shell permission. | | |
| TASK-016 | Define audit event schema for approval requested/resolved, command/action started, completed, denied, timed out, and failed. | | |

### GOAL-004: Build Native `system-gateway` Skeleton

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-017 | Create native service package under `services/system_gateway/` with `pyproject.toml`, `__main__.py`, config loading, and aiohttp server skeleton. | ✅ | 2026-06-23 |
| TASK-018 | Implement platform detection and adapter selection for Linux, macOS, and Windows. Unsupported platforms must start in read-only/no-shell mode or fail clearly. | ✅ | 2026-06-23 |
| TASK-019 | Implement `BaseSystemAdapter` interface for capabilities and structured actions. | ✅ | 2026-06-23 |
| TASK-020 | Implement Linux adapter for initial read-only structured actions without `nsenter`; assume native service runs on Linux host. | ✅ | 2026-06-23 |
| TASK-021 | Add macOS and Windows adapters as capability stubs with honest unsupported responses before adding OS-specific actions. | ✅ | 2026-06-23 |
| TASK-022 | Add process timeout/output truncation utilities that can later handle process groups per OS. | | |

### GOAL-005: Add Authentication And Approval Binding

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-023 | Replace `Origin` trust with signed requests or bearer/HMAC authentication between container clients and `system-gateway`. | | |
| TASK-024 | Add request nonce/timestamp handling to reduce replay risk for mutating/raw-shell operations. | | |
| TASK-025 | Bind execution to an approval record/id issued by `ApprovalGate`/Evernight for mutating actions and raw shell. | | |
| TASK-026 | Restrict channel approval buttons to authorized users; owner DM approval remains preferred for host gateway administration. | | |
| TASK-027 | Add tests for denied auth, stale signatures, missing approval id, unauthorized approver, timeout, and output truncation. | | |

### GOAL-006: Wire Evernight Monitor And Install Orchestration

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-028 | Add `twin/evernight/system_gateway/monitor.py` to check gateway health/capabilities/version and report degraded/missing state. | | |
| TASK-029 | Add owner-only Evernight commands or internal handlers for gateway status/doctor/update approval. Keep chat-platform specifics in adapters. | | |
| TASK-030 | Define first-run bootstrap flow: if native gateway is absent, Evernight sends an OS-specific one-time installer command for the owner to run manually. | | |
| TASK-031 | Define post-bootstrap update flow: if gateway is present and owner approves, Evernight can ask gateway to update/restart itself through a restricted updater endpoint. | | |
| TASK-032 | Replace Evernight self-heal direct `/execute` restart path with a structured `restart_allowed_container` action or keep it disabled until policy support exists. | | |

### GOAL-007: Packaging And CLI

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-033 | Add CLI entrypoint `system-gateway` with `status`, `doctor`, `capabilities`, `logs`, `pair`, `install`, `update`, and `uninstall` command stubs. | | |
| TASK-034 | Add Linux systemd unit under `services/system_gateway/packaging/linux/system-gateway.service`. | | |
| TASK-035 | Add macOS launchd plist under `services/system_gateway/packaging/macos/`. | | |
| TASK-036 | Add Windows packaging notes/stub under `services/system_gateway/packaging/windows/` before implementing Windows service support. | | |
| TASK-037 | Add `pair` flow for generating/storing shared auth material without printing secrets into logs. | | |

### GOAL-008: Documentation And Migration

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-038 | Update root README host-tool section from `execute_host_bash` to System Gateway architecture. | | |
| TASK-039 | Update `.agents/PROJECT_CONTEXT.md` runtime services and tool boundary after implementation lands. | | |
| TASK-040 | Update `.agents/AGENT_RULES.md` with System Gateway safety invariants: no `Origin` auth, no host-shell execution without approval id, no direct Evernight Redis or host bypass. | | |
| TASK-041 | Add `services/system_gateway/README.md` with threat model, supported OS matrix, bootstrap flow, and admin runbook. | | |
| TASK-042 | Add deprecation note for `execute_host_bash` and a cleanup plan for removing `bash-executor` once System Gateway reaches feature parity. | | |

## Test Plan

Focused unit tests:

```bash
conda run -n discord_bot python -m pytest tests/unit/tool_bootstrap_test.py tests/unit/tool_prompt_catalog_test.py -q
conda run -n discord_bot python -m pytest tests/unit/approval_gate_test.py -q
```

New tests to add:

```text
tests/unit/system_gateway_client_test.py
tests/services/tools/host_system_tool_test.py
tests/unit/system_gateway_policy_test.py
tests/unit/evernight_system_gateway_monitor_test.py
```

Native gateway tests:

```text
services/system_gateway/tests/test_capabilities.py
services/system_gateway/tests/test_auth.py
services/system_gateway/tests/test_policy.py
services/system_gateway/tests/test_server.py
services/system_gateway/tests/test_adapters_linux.py
```

Docker/runtime smoke after compatibility phase:

```bash
docker compose -f docker/docker-compose.yml ps
curl -sf http://localhost:8374/health
```

Manual acceptance when native gateway exists:

- `system-gateway status` reports running service and platform.
- `system-gateway capabilities` reports accurate OS features.
- March7 `host_system` read-only action succeeds after owner approval rules pass.
- Raw shell is denied by default.
- Mutating action without approval id is denied.
- Evernight monitor reports missing/outdated gateway without attempting unsafe
  automatic install.

## Assumptions

- The subsystem name is **System Gateway**.
- The native service command is `system-gateway`.
- The model-facing tool name is `host_system`.
- March7 uses host capabilities; Evernight monitors/administers them.
- First install cannot be fully automatic from Docker on every OS. A one-time
  owner-run bootstrap command is required unless a pre-existing trusted
  bootstrap agent or OS management credential is available.
- macOS/Windows support means native host service adapters, not Docker `nsenter`
  compatibility.
- The current `bash-executor` stays temporarily for continuity but is legacy
  Linux-only infrastructure.
