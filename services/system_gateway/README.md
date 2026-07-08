# System Gateway

Native host boundary for the Twin agent stack. `march7` and `evernight` run in
Docker, but host operations run through this service on the host OS. Agents do
not receive a general host shell; they call `host_system`, which signs requests
to System Gateway, and dangerous operations still require owner approval.

## Architecture

Directory ownership:

- `services/system_gateway/` is the native host service package. This is what
  gets installed into the host venv and runs as `system-gateway.service`.
- `twin/shared/system_gateway/` is shared protocol code: HMAC auth, request and
  response types, client errors, and `HostGatewayClient`.
- `twin/evernight/host_gateway/` is Evernight-side orchestration only:
  health monitor, `gateway_admin` bootstrap hints, and update requests. It is
  not a second service implementation.
- `scripts/bootstrap_system_gateway.py` is the one-command installer for the
  native service package in `services/system_gateway/`.

```mermaid
flowchart LR
    Owner["Owner in Discord"] -->|"asks Evernight"| EV["Evernight agent"]
    EV -->|"gateway_admin install"| Hint["host install command"]
    Owner -->|"runs command on host"| Host["Host OS"]
    Host -->|"creates venv + systemd unit"| SG["system-gateway :8380"]

    M7["March7 container"] -->|"host_system"| Client["HostGatewayClient"]
    EV -->|"host_system"| Client
    Client -->|"HMAC + nonce"| SG
    SG -->|"policy + approval token"| Shell["OS shell adapter"]
    Shell -->|"approved command"| Result["tool output"]

    SG --> Health["GET /health"]
    SG --> Caps["GET /capabilities"]
```

First install is special: when the service is missing, there is no host
execution channel yet. Evernight's `gateway_admin install` returns a
code-generated command for the owner to run on the host. It does not execute a
container-side bootstrap bridge.

After install, normal host interaction goes through `host_system` and
`HostGatewayClient`.

## Current Capabilities

- `GET /health` reports service status, version, uptime, and platform.
- `GET /capabilities` reports platform, shell, and feature metadata.
- `POST /shell/run` runs an owner-approved command on the platform shell.
- `POST /self/update` records an owner-approved update request; it does not
  download or restart binaries by itself.

Current adapters expose one generic shell path:

| Platform | Shell | Feature |
| --- | --- | --- |
| Linux | `/bin/sh` | `generic_shell_exec` |
| macOS | `/bin/zsh` | `generic_shell_exec` |
| Windows | `powershell.exe` | `generic_shell_exec` |

## Security Model

- `/health` and `/capabilities` are public for monitoring.
- Mutating endpoints require HMAC request signing with timestamp and nonce.
- Shell execution also requires a fresh owner approval token bound to action
  `shell` and the request actor.
- Approval tokens are single-use; replayed nonces are rejected.
- The Linux systemd unit runs from `/opt/system-gateway/venv/bin/python`, keeps
  `ProtectHome=true`, and reads the shared secret from
  `/etc/system-gateway/secret`.
- There is no Docker privileged host executor in the default stack.

## Quick Start

### Owner-Driven Install Hint

From Discord DM with Evernight:

```text
Evernight, cài lại System Gateway bằng gateway_admin install.
Sau khi xong gọi host_system capabilities.
```

Evernight returns the exact host command. Run it on the host, then ask
Evernight or March7 for `host_system capabilities` to verify the service.

### Manual Install Fallback

From the repo root on the host:

```bash
python3 scripts/bootstrap_system_gateway.py
```

The bootstrap script creates/syncs the shared secret, creates the venv, installs
the package, registers the native service, restarts it, and verifies `/health`.
On Linux it re-execs through `sudo` when root is required. If it writes a new
secret into `.env`, restart the Docker stack so containers pick up the value.

## Configuration

| Variable | Default | Used by |
| --- | --- | --- |
| `SYSTEM_GATEWAY_URL` | `http://host.docker.internal:8380` | containers |
| `SYSTEM_GATEWAY_HOST` | `127.0.0.1` | native service |
| `SYSTEM_GATEWAY_PORT` | `8380` | native service |
| `SYSTEM_GATEWAY_SHARED_SECRET` | unset | containers / signing |
| `SYSTEM_GATEWAY_SHARED_SECRET_FILE` | unset | systemd service |
| `SYSTEM_GATEWAY_RAW_SHELL` | `true` | emergency kill-switch |
| `SYSTEM_GATEWAY_BOOTSTRAP_REPO_ROOT` | unset | Evernight install hint |
| `SYSTEM_GATEWAY_BOOTSTRAP_VENV` | `/opt/system-gateway/venv` | bootstrap script |

Docker compose loads the shared secret from `.env` via `env_file`; do not set it
to an empty value in `environment:`.

## Operations

```bash
curl http://127.0.0.1:8380/health
curl http://127.0.0.1:8380/capabilities
systemctl status system-gateway --no-pager
journalctl -u system-gateway -f
```

Useful agent-facing checks:

```text
Evernight, gọi gateway_admin status rồi gọi host_system mode=capabilities.
Evernight, gọi host_system mode=shell command="printf system-gateway-ok && uname -s".
```

The second command should trigger owner approval before execution.

## Development And Tests

```bash
/home/flowerf/.conda/envs/discord_bot/bin/python -m pytest services/system_gateway/tests -q -p no:phoenix
/home/flowerf/.conda/envs/discord_bot/bin/python -m pytest \
  tests/unit/gateway_admin_tool_test.py \
  tests/unit/evernight_host_gateway_installer_test.py \
  tests/unit/system_gateway_cli_test.py \
  tests/unit/tool_bootstrap_test.py \
  -q -p no:phoenix
```

## Migration Note

The legacy Docker bash executor and hidden host-bash tool have been removed.
System Gateway is the only supported host boundary.
