---
goal: Implement MCP Streamable HTTP Transport (Phase 001)
version: "1.0"
date_created: "2026-05-07"
last_updated: "2026-05-07"
owner: Developer
status: 'Planned'
tags: [feature, mcp, transport, http, aiohttp]
---

# Phase 001: HTTPTransport Implementation

![Status: Planned](https://img.shields.io/badge/status-Planned-blue)

## Overview
Implement the `HTTPTransport` class in `src/services/tools/mcp_transport.py` to enable network-based MCP Client ↔ MCP Server communication via HTTP POST using JSON-RPC 2.0. The transport connects a Docker container-based MCP Client to a standalone HTTP Server running on the host at `http://host.docker.internal:8374/mcp`. This implementation follows the MCP Streamable HTTP transport specification, including `Mcp-Session-Id` header management for session persistence.

## Requirements
- **REQ-001**: `HTTPTransport.send_request()` sends JSON-RPC requests via HTTP POST with `Content-Type: application/json` and `Accept: application/json` headers
- **REQ-002**: `HTTPTransport` stores `Mcp-Session-Id` from initialize response headers and includes it in all subsequent requests
- **REQ-003**: `HTTPTransport.connect()` performs a health check by sending an `initialize` JSON-RPC request and validating the response
- **REQ-004**: `HTTPTransport` uses `aiohttp.ClientSession` with configurable timeout (default 30s)
- **REQ-005**: `HTTPTransport` handles connection errors, timeouts, and HTTP error status codes with descriptive exceptions
- **REQ-006**: `HTTPTransport.close()` properly closes the `aiohttp.ClientSession`
- **REQ-007**: `HTTPTransport.is_connected()` returns accurate connection state
- **REQ-008**: Server URL defaults to `http://host.docker.internal:8374/mcp` with fallback `http://172.17.0.1:8374/mcp`

## Constraints & Guidelines
- **CON-001**: `aiohttp` is already in `requirements.txt` — no new dependency needed
- **CON-002**: Follow existing project patterns: `TavilyClient` and `QwenService` use lazy session creation via `_get_session()` pattern
- **CON-003**: `MCPRequest.to_dict()` and `MCPResponse.from_dict()` are the serialization methods to use (already implemented in `mcp_protocol.py`)
- **CON-004**: `logging.getLogger(__name__)` is the project's logging convention
- **GUD-001**: Session lifecycle: `connect()` creates session, `close()` destroys it, `send_request()` reuses it
- **GUD-002**: Session ID is only set after a successful `initialize` response — `connect()` must send `initialize` request
- **GUD-003**: Use `aiohttp.ClientTimeout` for timeout configuration (consistent with `TavilyClient`)
- **PAT-001**: Strategy Pattern — `HTTPTransport` implements the `Transport` abstract base class

## Implementation Phases

### Phase 1: Core HTTP Request/Response Pipeline
**Goal**: GOAL-001 — Implement `send_request()` with HTTP POST, JSON serialization, and response parsing

| ID | Task | File(s) | Dependencies | Status | Completed |
|----|------|---------|--------------|--------|-----------|
| TASK-001 | Replace `HTTPTransport.send_request()` placeholder: serialize `MCPRequest` via `request.to_dict()`, POST to `self.server_url` with headers `Content-Type: application/json` and `Accept: application/json`, parse response JSON via `MCPResponse.from_dict()`, return `MCPResponse` | `src/services/tools/mcp_transport.py` | None | ☐ | |
| TASK-002 | Add `Mcp-Session-Id` header management: add `self._session_id: Optional[str] = None` to `__init__`; in `send_request()`, if `self._session_id` is set, include `Mcp-Session-Id: {self._session_id}` in request headers; after receiving response, extract `Mcp-Session-Id` from response headers via `response.headers.get("Mcp-Session-Id")` and store in `self._session_id` | `src/services/tools/mcp_transport.py` | TASK-001 | ☐ | |
| TASK-003 | Add `Origin` header to all requests: include `Origin: mcp-client` in request headers (per MCP spec, server validates this) | `src/services/tools/mcp_transport.py` | TASK-001 | ☐ | |

### Phase 2: Connection Lifecycle & Session Management
**Goal**: GOAL-002 — Implement `connect()`, `close()`, `is_connected()` with proper aiohttp session lifecycle

| ID | Task | File(s) | Dependencies | Status | Completed |
|----|------|---------|--------------|--------|-----------|
| TASK-004 | Implement `HTTPTransport.connect()`: create `aiohttp.ClientSession` with `aiohttp.ClientTimeout(total=self.timeout)`, set `self._session` and `self._connected = True`, send `MCPRequest(method="initialize")` via `send_request()`, validate response, log success | `src/services/tools/mcp_transport.py` | TASK-001, TASK-002 | ☐ | |
| TASK-005 | Implement `HTTPTransport.close()`: check `self._session` exists and is not closed, call `await self._session.close()`, set `self._session = None`, `self._connected = False`, `self._session_id = None`, log closure | `src/services/tools/mcp_transport.py` | TASK-004 | ☐ | |
| TASK-006 | Implement `HTTPTransport.is_connected()`: return `self._connected and self._session is not None and not self._session.closed` | `src/services/tools/mcp_transport.py` | TASK-004 | ☐ | |
| TASK-007 | Add lazy session helper `_get_session()`: pattern from `TavilyClient` — if `self._session` is None or closed, create new session; return `self._session`. `connect()` calls this, `send_request()` uses it. | `src/services/tools/mcp_transport.py` | TASK-004 | ☐ | |

### Phase 3: Error Handling & Resilience
**Goal**: GOAL-003 — Add comprehensive error handling for connection failures, timeouts, and HTTP errors

| ID | Task | File(s) | Dependencies | Status | Completed |
|----|------|---------|--------------|--------|-----------|
| TASK-008 | Add `aiohttp.ClientError` exception handling in `send_request()`: catch `aiohttp.ClientConnectionError` and raise `RuntimeError("MCP HTTP connection refused: {server_url}")` | `src/services/tools/mcp_transport.py` | TASK-001 | ☐ | |
| TASK-009 | Add `asyncio.TimeoutError` and `aiohttp.ServerTimeoutError` handling in `send_request()`: raise `TimeoutError(f"MCP HTTP request timed out after {self.timeout}s")` | `src/services/tools/mcp_transport.py` | TASK-001 | ☐ | |
| TASK-010 | Add HTTP error status handling in `send_request()`: for status 4xx/5xx, log error with status code and response body, raise `RuntimeError(f"MCP HTTP error {status}: {body}")` | `src/services/tools/mcp_transport.py` | TASK-001 | ☐ | |
| TASK-011 | Add JSON parse error handling: if response body is not valid JSON, log warning and raise `RuntimeError("Invalid JSON-RPC response from MCP server")` | `src/services/tools/mcp_transport.py` | TASK-001 | ☐ | |
| TASK-012 | Add `send_request()` guard: if `not self.is_connected()`, raise `RuntimeError("Transport is not connected — call connect() first")` (replace existing check that uses `self._connected` directly) | `src/services/tools/mcp_transport.py` | TASK-006 | ☐ | |

### Phase 4: Validation & Testing
**Goal**: GOAL-004 — Add unit tests for HTTPTransport and verify integration with MCPClient

| ID | Task | File(s) | Dependencies | Status | Completed |
|----|------|---------|--------------|--------|-----------|
| TASK-013 | Create test file `tests/test_mcp_http_transport.py` with `pytest-asyncio` test class `TestHTTPTransport` | `tests/test_mcp_http_transport.py` | None | ☐ | |
| TASK-014 | Add test `test_send_request_success`: mock `aiohttp.ClientSession.post()` to return 200 with valid JSON-RPC response, verify `MCPResponse` is returned with correct result | `tests/test_mcp_http_transport.py` | TASK-013 | ☐ | |
| TASK-015 | Add test `test_session_id_extraction`: mock response with `Mcp-Session-Id` header, verify transport stores it and includes it in next request | `tests/test_mcp_http_transport.py` | TASK-002, TASK-013 | ☐ | |
| TASK-016 | Add test `test_connection_refused`: mock `aiohttp` to raise `ClientConnectionError`, verify `RuntimeError` with "connection refused" message | `tests/test_mcp_http_transport.py` | TASK-008, TASK-013 | ☐ | |
| TASK-017 | Add test `test_timeout`: mock `aiohttp` to raise `ServerTimeoutError`, verify `TimeoutError` with timeout message | `tests/test_mcp_http_transport.py` | TASK-009, TASK-013 | ☐ | |
| TASK-018 | Add test `test_http_error`: mock response with status 500, verify `RuntimeError` with status code in message | `tests/test_mcp_http_transport.py` | TASK-010, TASK-013 | ☐ | |
| TASK-019 | Add test `test_connect_initializes_session`: call `connect()`, verify `_session` is created, `_connected` is True, `_session_id` is set from initialize response | `tests/test_mcp_http_transport.py` | TASK-004, TASK-013 | ☐ | |
| TASK-020 | Add test `test_close_clears_state`: call `connect()`, then `close()`, verify `_session` is None, `_connected` is False, `_session_id` is None | `tests/test_mcp_http_transport.py` | TASK-005, TASK-013 | ☐ | |
| TASK-021 | Add test `test_send_request_not_connected`: call `send_request()` without `connect()`, verify `RuntimeError` with "not connected" message | `tests/test_mcp_http_transport.py` | TASK-012, TASK-013 | ☐ | |
| TASK-022 | Run `pytest tests/test_mcp_http_transport.py -v` and verify all tests pass | `tests/test_mcp_http_transport.py` | TASK-014 through TASK-021 | ☐ | |

## Alternatives Considered
- **ALT-001**: Use `httpx` instead of `aiohttp` — Rejected: `aiohttp` is already a project dependency (used in `QwenService`, `GeminiService`, `TavilyClient`, etc.). Adding `httpx` would introduce an unnecessary second HTTP library.
- **ALT-002**: Create session per request (stateless) — Rejected: MCP Streamable HTTP spec requires session persistence via `Mcp-Session-Id` header. Connection pooling and session reuse is also more efficient.
- **ALT-003**: Use `requests` (sync) — Rejected: the entire project uses async/await patterns. Sync `requests` would block the event loop and break compatibility with `discord.py`'s async architecture.

## Dependencies
- **DEP-001**: `aiohttp` (>=3.8.0) — already in `requirements.txt`, used throughout project. No version conflict.
- **DEP-002**: `pytest-asyncio` (>=0.21.0) — already in `requirements.txt` via `pytest-asyncio` entry.
- **DEP-003**: `src.services.tools.mcp_protocol` — `MCPRequest`, `MCPResponse` models (already implemented).

## Affected Files
- **FILE-001**: `src/services/tools/mcp_transport.py` — modify — Replace `HTTPTransport` placeholder methods (`connect`, `send_request`, `close`, `is_connected`) with full implementation; add `_get_session()` helper and `_session_id` attribute
- **FILE-002**: `tests/test_mcp_http_transport.py` — create — Unit tests for `HTTPTransport` (tasks, session management, error handling)

## Testing Strategy
- **TEST-001**: Unit tests in `tests/test_mcp_http_transport.py` using `pytest-asyncio` with `unittest.mock.AsyncMock` to mock `aiohttp.ClientSession` and `aiohttp.ClientResponse`. Coverage target: 90%+ for `HTTPTransport` class.
- **TEST-002**: Integration test — after unit tests pass, run existing `tests/test_mcp_client.py` (if exists) or create manual test with `MCPClient(HTTPTransport(...))` to verify end-to-end flow: `connect()` → `list_tools()` → `call_tool()` → `close()`.
- **TEST-003**: Error path coverage — each error handler (connection refused, timeout, HTTP 4xx/5xx, invalid JSON) has a dedicated test case (TASK-016 through TASK-018).

## Risks
- **RISK-001**: MCP HTTP Server at `host.docker.internal:8374` may not be running during development — Impact: High, Likelihood: Medium. Mitigation: Tests use mocks; integration tests require manual server startup. Add fallback URL `172.17.0.1:8374` for Docker networking issues.
- **RISK-002**: `aiohttp` session lifecycle — if server closes connection unexpectedly, `self._session.closed` may not reflect reality until next request — Impact: Medium, Likelihood: Low. Mitigation: `_get_session()` checks `self._session.closed` and recreates session if needed.
- **RISK-003**: `Mcp-Session-Id` header name may vary — some servers use lowercase `mcp-session-id` — Impact: Medium, Likelihood: Low. Mitigation: Use case-insensitive header lookup (`response.headers.get("Mcp-Session-Id")` — aiohttp headers are case-insensitive by default).

## Assumptions
- **ASSUMPTION-001**: MCP HTTP Server follows the official MCP Streamable HTTP spec (returns `Mcp-Session-Id` in initialize response headers)
- **ASSUMPTION-002**: MCP Server at `:8374/mcp` endpoint is already deployed and accessible from Docker container
- **ASSUMPTION-003**: `initialize` method is the first request sent during `connect()` — server expects this per MCP spec
- **ASSUMPTION-004**: SSE (Server-Sent Events) via GET request is out of scope for Phase 001 — will be implemented in a future phase for server-initiated notifications

## Related Resources
- MCP Streamable HTTP Spec: https://modelcontextprotocol.io/specification/2024-11-05/basic/transports#streamable-http
- JSON-RPC 2.0 Spec: https://www.jsonrpc.org/specification
- aiohttp Documentation: https://docs.aiohttp.org/en/stable/
- Project `TavilyClient` (reference for aiohttp session pattern): `src/services/external/tavily_client.py`
- Project `MCPClient` (consumer of this transport): `src/services/tools/mcp_client.py`
- MCP Protocol models: `src/services/tools/mcp_protocol.py`
