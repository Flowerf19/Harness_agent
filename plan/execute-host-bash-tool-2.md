# Plan: Execute Host Bash Tool + HTTP Transport

**Status**: Draft
**Created**: 2026-05-06
**Goal**: Thêm tool `execute_host_bash` cho phép LLM chạy bash commands trên host machine qua MCP Streamable HTTP transport.

---

## Scope

### In scope (phase này)
1. Implement `HTTPTransport` (MCP Client → MCP Server qua HTTP)
2. Tạo standalone MCP HTTP Server trên host
3. Tạo `execute_host_bash_tool.py`
4. Update `dependencies.py` — optionally dùng HTTPTransport
5. Setup script + systemd template

### Not in scope (sẽ làm sau)
- **Trạm Gác (approval gate)**: Discord button approve/reject
- **Security rules trong `security.md`**: Blacklist/whitelist commands
- **Multi-user permission**: Permission theo role/user
- **Command audit log**: Lịch sử lệnh đã chạy

---

## Architecture Overview

```
┌────────────────────────────────────────────────┐
│  Docker Container (Fedora)                     │
│                                                │
│  Bot → ChatCoordinator → MCPClient             │
│                ↓                               │
│         HTTPTransport                          │
│         POST http://host.docker.internal:8374/mcp │
└──────────────────┬─────────────────────────────┘
                   │ HTTP (JSON-RPC)
                   │ Mcp-Session-Id header
                   ▼
┌────────────────────────────────────────────────┐
│  Host (Ubuntu/Fedora)                          │
│                                                │
│  MCP HTTP Server (standalone, port 8374)       │
│    ├─ ToolRegistry                             │
│    │   └─ ExecuteHostBashTool                  │
│    └─ asyncio.subprocess → host bash           │
└────────────────────────────────────────────────┘
```

---

## Phases

### PHASE-001: HTTPTransport Implementation

**Why**: MCP Client cần giao tiếp với MCP Server qua mạng, không còn in-process.
**Dependencies**: None (dựa trên existing `mcp_transport.py` skeleton)

| Task | Description | Files | Acceptance Criteria |
|------|-------------|-------|---------------------|
| TASK-001 | Implement `HTTPTransport.send_request()` | `src/services/tools/mcp_transport.py` | POST JSON-RPC tới HTTP endpoint, parse response thành `MCPResponse` |
| TASK-002 | Implement `HTTPTransport.close()` + `is_connected()` | `src/services/tools/mcp_transport.py` | Đóng session, cleanup HTTP client |
| TASK-003 | Handle `Mcp-Session-Id` header | `src/services/tools/mcp_transport.py` | Session ID từ response `initialize` được lưu và attach vào mọi request sau |
| TASK-004 | Error handling: connection refused, timeout, HTTP error | `src/services/tools/mcp_transport.py` | Raise descriptive errors cho từng case |
| TASK-005 | Add `aiohttp` hoặc `httpx` vào `requirements.txt` | `requirements.txt` | Dependency available |

### PHASE-002: Standalone MCP HTTP Server

**Why**: MCP Server cần chạy như standalone process trên host, nhận HTTP requests.
**Dependencies**: PHASE-001 (cùng protocol)

| Task | Description | Files | Acceptance Criteria |
|------|-------------|-------|---------------------|
| TASK-006 | Tạo `src/server/__init__.py` | `src/server/__init__.py` | Module exists |
| TASK-007 | Tạo `src/server/mcp_http_server.py` — aiohttp server với `/mcp` endpoint | `src/server/mcp_http_server.py` | Server nghe trên `0.0.0.0:8374`, nhận POST JSON-RPC |
| TASK-008 | Implement `/mcp` POST handler → route tới MCPServer | `src/server/mcp_http_server.py` | JSON-RPC request → MCPServer.handle_request() → JSON-RPC response |
| TASK-009 | Implement session management (`Mcp-Session-Id`) | `src/server/mcp_http_server.py` | Mỗi client có session riêng, header validation |
| TASK-010 | Implement Origin header validation (DNS rebinding prevention) | `src/server/mcp_http_server.py` | Reject request nếu Origin không khớp |
| TASK-011 | Tool discovery trong standalone server | `src/server/mcp_http_server.py` | Auto-discover tools từ `implementations/` directory |
| TASK-012 | Tạo `src/server/config.py` — server config (port, allowed origins, etc.) | `src/server/config.py` | Configurable qua env vars |

### PHASE-003: ExecuteHostBashTool

**Why**: Tool chính để LLM chạy bash commands trên host.
**Dependencies**: PHASE-002 (server chạy được tool)

| Task | Description | Files | Acceptance Criteria |
|------|-------------|-------|---------------------|
| TASK-013 | Tạo `execute_host_bash_tool.py` với BaseTool interface | `src/services/tools/implementations/execute_host_bash_tool.py` | Class kế thừa BaseTool, có `name`, `description`, `parameters_schema`, `execute()` |
| TASK-014 | Implement `execute()` với `asyncio.subprocess` | `src/services/tools/implementations/execute_host_bash_tool.py` | Chạy lệnh thật trên host, capture stdout/stderr |
| TASK-015 | Timeout parameter (LLM quyết định, required param) | `src/services/tools/implementations/execute_host_bash_tool.py` | Schema có `timeout` (int, required), áp dụng cho subprocess |
| TASK-016 | Output truncation (8000 chars max) | `src/services/tools/implementations/execute_host_bash_tool.py` | Output > 8000 chars → cắt giữ đầu+cuối, thêm "[truncated]" |
| TASK-017 | Markdown cleanup (loại bỏ ```bash ... ```) | `src/services/tools/implementations/execute_host_bash_tool.py` | LLM gửi markdown → tự động clean |
| TASK-018 | Register tool trong discovery system | Auto-discovery | Tool được auto-discover khi file tồn tại |

### PHASE-004: Update dependencies.py

**Why**: Bot cần optionally dùng HTTPTransport thay vì InMemoryTransport.
**Dependencies**: PHASE-001

| Task | Description | Files | Acceptance Criteria |
|------|-------------|-------|---------------------|
| TASK-019 | Thêm config `MCP_SERVER_URL` (env var) | `src/config/settings.py` | Config field mới |
| TASK-020 | Conditional transport selection trong `AppContainer.initialize()` | `src/services/dependencies.py` | Nếu `MCP_SERVER_URL` set → HTTPTransport, ngược lại → InMemoryTransport |
| TASK-021 | Backward compatible test | `src/services/dependencies.py` | Bot vẫn chạy bình thường nếu không set `MCP_SERVER_URL` |

### PHASE-005: Setup Scripts

**Why**: End user cần dễ dàng setup MCP Server trên host.
**Dependencies**: PHASE-002

| Task | Description | Files | Acceptance Criteria |
|------|-------------|-------|---------------------|
| TASK-022 | Tạo `scripts/start_mcp_server.sh` — start MCP HTTP server | `scripts/start_mcp_server.sh` | Script chạy `python -m src.server.mcp_http_server` với env vars |
| TASK-023 | Tạo `scripts/setup_mcp_server.sh` — one-time setup | `scripts/setup_mcp_server.sh` | Install deps, tạo `.env` từ template, verify server chạy |
| TASK-024 | Tạo `docker/mcp-server.service` — systemd template | `docker/mcp-server.service` | Service file template, user copy vào `/etc/systemd/system/` |
| TASK-025 | Update `docker/docker-compose.bot.yml` — thêm `host.docker.internal` mapping | `docker/docker-compose.bot.yml` | Bot container có thể reach `http://host.docker.internal:8374` |

---

## Execution Order

```
PHASE-001 (HTTPTransport)
    ↓
PHASE-002 (Standalone MCP Server)
    ↓
PHASE-003 (ExecuteHostBashTool)
    ↓
PHASE-004 (Update dependencies.py)
    ↓
PHASE-005 (Setup Scripts)
```

---

## Risk & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| `aiohttp` conflict với existing deps | Medium | Check `requirements.txt` trước khi thêm |
| `host.docker.internal` không hoạt động trên Linux | Medium | Dùng `--network=host` hoặc `172.17.0.1` (Docker bridge gateway) làm fallback |
| Security: LLM chạy lệnh destructive (`rm -rf`) | High | Phase sau: security.md rules; Phase này auto-execute |
| MCP Server crash → bot không dùng được tool | Medium | Fallback về InMemoryTransport nếu HTTP connection failed |

---

## Testing Strategy

| What | How |
|------|-----|
| HTTPTransport | Unit test: mock HTTP client, verify JSON-RPC send/receive |
| MCP HTTP Server | Integration test: start server, POST request, verify response |
| ExecuteHostBashTool | Unit test: mock subprocess, verify timeout, truncation, cleanup |
| End-to-end | Manual test: run bot + MCP server, ask LLM to run `docker ps` |
