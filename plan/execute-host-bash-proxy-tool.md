---
goal: Implement ExecuteHostBashTool với ApprovalGate + Host Bash Executor (Proxy Tool Pattern)
version: "3.0"
date_created: "2026-05-07"
last_updated: "2026-05-07"
owner: Developer
status: Completed
tags: [feature, mcp, tool, host, bash, security, approval-gate]
---

# Plan: Execute Host Bash Proxy Tool

## Triết lý thiết kế

**Proxy Tool Pattern** — `execute_host_bash` là một `BaseTool` bình thường, nằm chung `ToolRegistry` với 5 tool hiện có. Bên trong `execute()`, tool tự gọi HTTP ra host và tự check `ApprovalGate`. **Không thay đổi ChatCoordinator, MCPClient, hay MCPServer.**

```
┌────────────────────────────────────────────────────────┐
│  CONTAINER (march7_bot)         ← KHÔNG THAY ĐỔI       │
│                                                        │
│  ChatCoordinator → MCPServer → ToolRegistry            │
│    ├── SearchMemoryTool                                 │
│    ├── WebSearchTool                                    │
│    ├── ExecuteHostBashTool  ← PROXY TOOL               │
│    │   ├── ApprovalGate.check()                        │
│    │   └── HTTP POST host:8374/execute                 │
│    └── ...                                              │
└──────────────────────┬─────────────────────────────────┘
                       │ HTTP
                       ▼
┌────────────────────────────────────────────────────────┐
│  HOST                        ← Bash Executor (tối giản) │
│  POST /execute {command, timeout}                       │
│  → asyncio.subprocess → {stdout, stderr, exit_code}    │
└────────────────────────────────────────────────────────┘
```

---

## Scope

### Phase này
1. `ApprovalGate` skeleton (auto-approve + log + hook cho Discord UI)
2. `ExecuteHostBashTool` (BaseTool, proxy pattern)
3. Host `Bash Executor` (aiohttp endpoint, KHÔNG phải full MCP Server)
4. Dependency injection trong `dependencies.py`
5. Config trong `settings.py`
6. Script khởi động + systemd template
7. Hướng dẫn sử dụng + cảnh báo bảo mật

### KHÔNG làm trong phase này
- Discord button UI trong ApprovalGate (phase 2)
- Security whitelist/blacklist commands (phase 2)
- Command audit log (phase 2)
- Agent tự động tạo tool (phase tương lai, không liên quan đến plan này)

---

## Kiến trúc chi tiết

### Luồng thực thi

```
User: "máy nóng quá, check nhiệt độ"
  │
  ▼
Agent Loop (ChatCoordinator)     ← KHÔNG THAY ĐỔI
  │
  ├─ LLM quyết định gọi execute_host_bash(command="sensors")
  │
  ├─ MCPServer._handle_tools_call()  ← KHÔNG THAY ĐỔI
  │   └─ registry.execute_tool("execute_host_bash", {command: "sensors"})
  │
  └─ ExecuteHostBashTool.execute(command="sensors")
       │
       ├─ 1. Clean markdown: ```bash sensors ``` → "sensors"
       │
       ├─ 2. ApprovalGate.check_approval("execute_host_bash", "sensors")
       │     ├─ Phase 1: log warning + auto-approve → return True
       │     └─ Phase 2: Discord message + nút [Approve][Reject] → wait interaction
       │
       ├─ 3. HTTP POST http://host.docker.internal:8374/execute
       │     Body: {command: "sensors", timeout: 30}
       │     Headers: {Origin: "march7-bot"}
       │
       ├─ 4. Host bash executor:
       │     ├─ Validate Origin header
       │     ├─ asyncio.create_subprocess_shell(command)
       │     ├─ Capture stdout/stderr với timeout
       │     └─ Return {stdout, stderr, exit_code}
       │
       └─ 5. Format kết quả → LLM sinh câu trả lời
```

### Phân biệt với các tool khác

| Tool | Transport | Approval | Host access |
|------|-----------|----------|-------------|
| `search_memory` | In-process | No | No |
| `web_search` | HTTP (Tavily API) | No | No |
| `run_python_code` | HTTP (CodeBox Docker) | No | No |
| **`execute_host_bash`** | **HTTP (Bash Executor)** | **YES** | **YES** |

TavilySearchTool đã làm pattern y hệt: BaseTool trong registry, execute() gọi HTTP ra ngoài. execute_host_bash chỉ thêm ApprovalGate — không có gì mới về mặt kiến trúc.

---

## Files to Create

| # | File | Mô tả | Dòng (ước tính) |
|---|------|-------|-----------------|
| 1 | `src/services/tools/approval_gate.py` | Trạm Gác - approve/reject logic + hook | ~60 |
| 2 | `src/services/tools/implementations/execute_host_bash_tool.py` | Tool proxy chính | ~200 |
| 3 | `src/server/__init__.py` | Module marker | ~3 |
| 4 | `src/server/bash_executor.py` | Host HTTP endpoint chạy bash | ~80 |
| 5 | `src/server/config.py` | Config cho bash executor | ~30 |
| 6 | `scripts/start_bash_executor.sh` | Script khởi động | ~20 |
| 7 | `scripts/setup_bash_executor.sh` | Script cài đặt one-time | ~40 |
| 8 | `docker/bash-executor.service` | systemd template | ~15 |

## Files to Modify

| # | File | Thay đổi |
|---|------|----------|
| 9 | `src/config/settings.py` | Thêm `BASH_EXECUTOR_URL`, `BASH_EXECUTOR_TIMEOUT`, `BASH_EXECUTOR_ALLOWED_ORIGINS` |
| 10 | `src/services/dependencies.py` | Tạo `ApprovalGate`, inject vào tool dependency |
| 11 | `src/services/tools/implementations/__init__.py` | Export `ExecuteHostBashTool` |

### Files KHÔNG thay đổi

- `src/services/chat_coordinator.py`
- `src/services/tools/mcp_client.py`
- `src/services/tools/mcp_server.py`
- `src/services/tools/mcp_transport.py`
- `src/services/tools/tool_registry.py`
- `src/services/tools/tool_discovery.py`

---

## Phases

### PHASE 1: ApprovalGate Skeleton

| ID | Task | File | AC |
|----|------|------|-----|
| TASK-001 | Tạo `ApprovalGate` class với `check_approval(tool_name, command)` | `src/services/tools/approval_gate.py` | async, return bool |
| TASK-002 | Log khi có approval request | `src/services/tools/approval_gate.py` | Log WARNING |
| TASK-003 | `_request_user_approval()` hook placeholder | `src/services/tools/approval_gate.py` | async, return True, docstring về Phase 2 |

### PHASE 2: ExecuteHostBashTool

| ID | Task | File | AC |
|----|------|------|-----|
| TASK-004 | Tạo class `ExecuteHostBashTool(BaseTool)` | `src/services/tools/implementations/execute_host_bash_tool.py` | name, description, parameters_schema |
| TASK-005 | Constructor nhận `approval_gate`, `executor_url`, `timeout` | same | Default từ Config |
| TASK-006 | Implement `execute(command, timeout)` | same | ApprovalGate → HTTP POST → format result |
| TASK-007 | `_clean_command()` - loại bỏ markdown | same | Xử lý ```bash, ```sh, ```shell |
| TASK-008 | `_format_result()` - format stdout/stderr | same | Truncate 8000, exit code, phân biệt streams |
| TASK-009 | `_get_session()` - lazy aiohttp session | same | Pattern từ TavilyClient |
| TASK-010 | Error handling: connection, timeout, HTTP error | same | Message tiếng Việt |
| TASK-011 | Export `ExecuteHostBashTool` | `src/services/tools/implementations/__init__.py` | Thêm vào `__all__` |

**Tool Schema:**

```python
name = "execute_host_bash"

parameters_schema = {
    "type": "object",
    "properties": {
        "command": {"type": "string", "description": "Lệnh bash. VD: 'sensors', 'docker ps', 'df -h'"},
        "timeout": {"type": "integer", "description": "Timeout (giây), mặc định 30, tối đa 120"}
    },
    "required": ["command"]
}
```

### PHASE 3: Host Bash Executor

> **ĐÂY KHÔNG PHẢI MCP SERVER.** HTTP endpoint đơn giản, không JSON-RPC, không ToolRegistry.

| ID | Task | File | AC |
|----|------|------|-----|
| TASK-012 | Tạo `src/server/__init__.py` | `src/server/__init__.py` | Module marker |
| TASK-013 | Tạo `src/server/config.py` | `src/server/config.py` | `BASH_EXECUTOR_PORT`, `HOST`, `ALLOWED_ORIGINS` |
| TASK-014 | Tạo `BashExecutor` aiohttp app | `src/server/bash_executor.py` | `POST /execute`, `GET /health` |
| TASK-015 | `POST /execute` handler | same | `{command, timeout}` → subprocess → `{stdout, stderr, exit_code}` |
| TASK-016 | Origin validation | same | Chỉ origin trong `ALLOWED_ORIGINS` |
| TASK-017 | Subprocess + timeout | same | `create_subprocess_shell`, `wait_for`, kill nếu quá |
| TASK-018 | Output truncation 8000 chars | same | Mỗi stream riêng, thêm `[truncated]` |
| TASK-019 | `GET /health` | same | `{"status": "ok", "uptime": ...}` |
| TASK-020 | `__main__` block | same | `python -m src.server.bash_executor` |

### PHASE 4: Config & DI

| ID | Task | File | AC |
|----|------|------|-----|
| TASK-021 | `BASH_EXECUTOR_URL` | `src/config/settings.py` | Default `http://host.docker.internal:8374` |
| TASK-022 | `BASH_EXECUTOR_TIMEOUT` | `src/config/settings.py` | Default `30` |
| TASK-023 | `BASH_EXECUTOR_ALLOWED_ORIGINS` | `src/config/settings.py` | Default `["march7-bot"]` |
| TASK-024 | Tạo `ApprovalGate` trong `initialize()` | `src/services/dependencies.py` | Instance duy nhất |
| TASK-025 | `approval_gate` vào `tool_dependencies` | `src/services/dependencies.py` | Key `"approval_gate"` |
| TASK-026 | `executor_url` vào `tool_dependencies` | `src/services/dependencies.py` | Key `"executor_url"` |

### PHASE 5: Scripts & Deployment

| ID | Task | File | AC |
|----|------|------|-----|
| TASK-027 | `scripts/setup_bash_executor.sh` | setup script | Kiểm tra Python, cài aiohttp, tạo env |
| TASK-028 | `scripts/start_bash_executor.sh` | start script | Export env, chạy `python -m src.server.bash_executor` |
| TASK-029 | `docker/bash-executor.service` | systemd template | User, WorkingDirectory, ExecStart |
| TASK-030 | `README_BASH_EXECUTOR.md` | Hướng dẫn | Cài đặt + bảo mật + ví dụ test |

### PHASE 6: Documentation

| ID | Task | Mô tả |
|----|------|-------|
| TASK-031 | Hướng dẫn cài đặt step-by-step | Clone, setup, start, verify |
| TASK-032 | Cảnh báo bảo mật | Risks + mitigations |
| TASK-033 | Ví dụ test an toàn | `sensors`, `df -h`, `docker ps` |
| TASK-034 | Gỡ cài đặt | Dừng service, xóa file |

---

## Security Model

```
     LỚP 1: LLM quyết định gọi tool
              ↓
     LỚP 2: ApprovalGate ← CHẶN + LOG
              ↓
     LỚP 3: Origin Validation (Host)
              ↓
     LỚP 4: OS non-root user
```

## ⚠️ Cảnh Báo Cho Người Dùng

| Risk | Mức độ | Mô tả |
|------|--------|-------|
| Prompt injection dẫn đến lệnh phá hoại | **CAO** | `rm -rf`, `shutdown`, xóa container |
| Lộ thông tin nhạy cảm | Trung bình | Đọc `.env`, token |
| Resource exhaustion | Trung bình | Fork bomb, chiếm CPU |

**Biện pháp đã có:** ApprovalGate, non-root user, Origin validation, timeout, output truncation.

**Khuyến nghị:** Chạy bash executor trong VM riêng, firewall IP, kiểm tra log định kỳ, backup.

---

## Verification Checklist

- [ ] Bot khởi động, log hiện "Discovered: ExecuteHostBashTool"
- [ ] `curl http://localhost:8374/health` → `{"status": "ok"}`
- [ ] Chat: "kiểm tra RAM máy" → bot gọi tool → kết quả `free -h`
- [ ] Log hiện "APPROVAL REQUESTED: execute_host_bash -> ..."
- [ ] Tool chạy non-root, không sudo
- [ ] POST từ origin lạ → 403
