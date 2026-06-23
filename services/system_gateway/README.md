# System Gateway

Native host service scaffold for shared Twin system capabilities.

This initial version exposes only read-only service metadata:

- `GET /health`
- `GET /capabilities`

It does not execute commands, enforce policy, install itself, or expose any
agent-facing tool endpoint.

## Run

From this directory:

```bash
python -m system_gateway
```

Optional environment variables:

- `SYSTEM_GATEWAY_HOST` defaults to `127.0.0.1`
- `SYSTEM_GATEWAY_PORT` defaults to `8765`
