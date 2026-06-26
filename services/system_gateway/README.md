# System Gateway

Native host service for the Twin agent stack. It is the single host boundary
between the March7 / Evernight containers and the real operating system.

The service runs on the host OS (not inside Docker), binds to localhost by
default, and exposes a small HTTP API. Every mutating request must be signed
with HMAC-SHA256 and carry a fresh, action-bound approval token issued by the
owner approval path.

## What it does

- **Capability discovery** — containers call `GET /capabilities` to learn what
the host supports (platform, shells, Docker, structured actions, raw-shell
policy).
- **Read-only structured actions** — `POST /actions/run` executes safe,
validated actions such as `system.status`, `system.disk_usage`,
`docker.list_containers`, `docker.container_logs`, and `service.status`.
- **Raw shell gate** — `POST /shell/run` is denied by default. It can only be
enabled with `SYSTEM_GATEWAY_RAW_SHELL=true` and still requires a valid
approval token.
- **Owner approval binding** — mutating actions and raw shell require an
approval token minted by Evernight / the owner CLI and bound to the exact
action and actor.
- **Audit** — every request lifecycle event is recorded:
  `APPROVAL_RESOLVED`, `ACTION_STARTED`, `ACTION_COMPLETED`, `ACTION_FAILED`,
  `ACTION_TIMED_OUT`, `ACTION_DENIED`.
- **Self-update hook** — `POST /self/update` accepts an owner-approved update
request and returns a queued status. The service does **not** auto-download or
restart itself; the admin must run the package update out-of-band.

## Supported platforms

| Platform | Adapter | Service packaging | Notes |
|----------|---------|-------------------|-------|
| Linux    | `system_gateway.adapters.linux` | systemd unit | Full structured actions, no `nsenter` |
| macOS    | `system_gateway.adapters.macos` | launchd plist | Capability stub; OS-specific actions later |
| Windows  | `system_gateway.adapters.windows` | Manual / service wrapper stub | Capability stub |

The service starts in read-only/no-shell mode on any platform; unsupported
actions are rejected with an honest `action_not_supported` response.

## Threat model

- **Trust boundary**: the service is the only process that executes host
commands. Containers must never shell out to the host directly.
- **Authentication**: request signatures use a shared HMAC secret. The same
secret derives approval-token HMACs in the current phase; the approval path
should later use a separate approval-only key.
- **Authorization**: deny by default. Read-only structured actions require a
valid request signature. Mutating actions and raw shell additionally require a
single-use, action-bound, actor-bound approval token.
- **Replay protection**: nonces are tracked in memory within a TTL window.
Approval-token nonces are consumed atomically.
- **Input validation**: all subprocess calls use explicit arg-lists
(`asyncio.create_subprocess_exec`), never `shell=True`. Paths and service
names are validated before reaching the OS.
- **Network exposure**: binds to `127.0.0.1:8380` by default. Do not expose it
to the network without a TLS-terminating reverse proxy and strong
authentication.

## Quick start

### 1. Install

From the repo root:

```bash
pip install -e services/system_gateway
system-gateway pair
system-gateway install
```

`pair` generates `/etc/system-gateway/secret` (Linux) or
`~/Library/Application Support/system-gateway/secret` (macOS) with owner-only
permissions. `install` deploys the systemd/launchd unit and points it at that
secret file.

### 2. Verify

```bash
system-gateway doctor
```

Expected output: healthy, with platform, version, and structured actions listed.

### 3. Wire the agents

Ensure the March7 / Evernight containers can reach the gateway and share the
secret:

```bash
# In the host env or .env that launches Docker Compose
export SYSTEM_GATEWAY_URL=http://host.docker.internal:8380
export SYSTEM_GATEWAY_SHARED_SECRET=$(cat /etc/system-gateway/secret)
```

`SYSTEM_GATEWAY_URL` is read by the agents; `SYSTEM_GATEWAY_SHARED_SECRET` is
used by `HostGatewayClient` to sign requests and mint approval tokens.

## Admin runbook

### Status and capabilities

```bash
system-gateway status
system-gateway capabilities
```

### Logs

```bash
system-gateway logs      # Linux: journalctl -u system-gateway -f
                         # macOS: log stream --predicate 'process == "system-gateway"'
```

### Update

```bash
# 1. Owner requests an update token
system-gateway update --target-version 0.2.0

# 2. Apply the package update out-of-band, then restart
sudo systemctl restart system-gateway   # Linux
```

The gateway's `POST /self/update` only records the request; it does not
auto-install binaries.

### Rotate the shared secret

```bash
system-gateway pair --force
sudo systemctl restart system-gateway   # Linux
```

Then update `SYSTEM_GATEWAY_SHARED_SECRET` in the container environment.

### Uninstall

```bash
system-gateway uninstall
```

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `SYSTEM_GATEWAY_HOST` | `127.0.0.1` | Bind host |
| `SYSTEM_GATEWAY_PORT` | `8380` | Bind port |
| `SYSTEM_GATEWAY_SHARED_SECRET` | — | HMAC shared secret |
| `SYSTEM_GATEWAY_SHARED_SECRET_FILE` | — | Path to secret file (used by systemd/launchd units) |
| `SYSTEM_GATEWAY_RAW_SHELL` | `false` | Enable raw-shell endpoint (still requires approval) |

## API endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET`  | `/health` | none | Service health, version, uptime, platform |
| `GET`  | `/capabilities` | none | Host capabilities |
| `POST` | `/actions/run` | HMAC + approval token | Execute a structured action |
| `POST` | `/shell/run` | HMAC + approval token | Raw shell gate (denied by default) |
| `POST` | `/self/update` | HMAC + approval token | Owner-approved update request |

## Development

Run the service in the foreground:

```bash
SYSTEM_GATEWAY_SHARED_SECRET=dev-secret system-gateway run
```

Run tests:

```bash
PYTHONPATH=/home/flowerf/Projects/march7:/home/flowerf/Projects/march7/services \
  conda run -n discord_bot python -m pytest services/system_gateway/tests/ -q
```

## Migration from `execute_host_bash`

`execute_host_bash` and the Docker `bash-executor` are legacy Linux-only
infrastructure. They are hidden from the model-facing tool catalog. New host
interactions must go through `host_system` → `HostGatewayClient` → native
`system-gateway`. The bash-executor may be removed once all host workflows are
ported to structured actions.
