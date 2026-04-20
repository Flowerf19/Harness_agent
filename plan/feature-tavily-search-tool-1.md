---
goal: Thêm Tavily Web Search MCP Tool cho Discord Bot - Tích hợp web search capability sử dụng Tavily API
version: 1.0
date_created: 2026-04-20
last_updated: 2026-04-20
owner: Flowerf
status: 'Planned'
tags: ['feature', 'mcp-tool', 'web-search', 'tavily', 'integration']
---

# Introduction

![Status: Planned](https://img.shields.io/badge/status-Planned-blue)

Plan này thêm **Tavily Web Search Tool** vào Discord Bot - một MCP tool cho phép bot:
1. **Web Search**: Tìm kiếm thông tin real-time từ internet
2. **Tavily API**: Sử dụng Tavily API (https://app.tavily.com) - chuyên dụng cho AI agents
3. **MCP Integration**: Tích hợp với hệ thống MCP tool hiện có
4. **Auto-Discovery**: Tự động được phát hiện và đăng ký bởi ToolDiscovery

## 0. Tavily API Overview

### Tavily Search API
- **Endpoint**: `https://api.tavily.com/search`
- **Method**: POST
- **Auth**: API Key trong header `Authorization: Bearer {api_key}`
- **Response**: JSON với `results` array chứa các search results

### Request Parameters
```json
{
  "query": "search query string",
  "search_depth": "basic" | "advanced",
  "max_results": 1-10,
  "include_answer": true/false,
  "include_raw_content": false,
  "include_images": false
}
```

### Response Format
```json
{
  "answer": "AI-generated answer (optional)",
  "results": [
    {
      "title": "Page title",
      "url": "https://...",
      "content": "Page content/snippet",
      "score": 0.95
    }
  ]
}
```

## 1. Requirements & Constraints

- **REQ-001**: Tool phải tìm kiếm web thông qua Tavily API
- **REQ-002**: Tool phải tuân thủ BaseTool interface (name, description, parameters_schema, execute)
- **REQ-003**: Tool phải được auto-discovered bởi ToolDiscovery
- **REQ-004**: Tool phải xử lý errors gracefully và trả về message thân thiện
- **REQ-005**: Tool phải hỗ trợ configuration qua environment variables
- **REQ-006**: Tool phải async và non-blocking
- **SEC-001**: API key không được log hoặc expose trong error messages
- **SEC-002**: Validate API key availability trước khi execute
- **PER-001**: Timeout hợp lý cho API calls (default 30s)
- **PER-002**: Cache hoặc rate limiting considerations
- **CON-001**: Tool phải hoạt động ngay cả khi Tavily API unavailable (graceful degradation)
- **CON-002**: Sử dụng aiohttp hiện có (không thêm dependency mới)
- **CON-003**: Follow coding conventions hiện có (Vietnamese comments, type hints)
- **GUD-001**: Follow BaseTool pattern như SearchMemoryTool
- **GUD-002**: Logging với logger.info/warning/error
- **GUD-003**: Dependency injection qua constructor
- **GUD-004**: Tool description bằng tiếng Việt (LLM hiểu tiếng Việt)
- **GUD-005**: Error messages thân thiện cho user
- **PAT-001**: Template Method Pattern (kế thừa BaseTool)
- **PAT-002**: Dependency Injection (TavilyClient injected vào Tool)
- **PAT-003**: Async/Await pattern cho non-blocking operations

## 2. Implementation Steps

### Implementation Phase 1: Environment Configuration

- GOAL-001: Thêm Tavily configuration vào settings và environment

| Task ID | Description | Status |
|---------|-------------|--------|
| TASK-001 | Thêm `TAVILY_API_KEY` vào `src/config/settings.py` | Pending |
| TASK-002 | Thêm `TAVILY_API_URL` (default: `https://api.tavily.com`) vào `settings.py` | Pending |
| TASK-003 | Thêm `TAVILY_MAX_RESULTS` (default: 5) vào `settings.py` | Pending |
| TASK-004 | Thêm `TAVILY_SEARCH_DEPTH` (default: "basic") vào `settings.py` | Pending |
| TASK-005 | Thêm `TAVILY_TIMEOUT` (default: 30) vào `settings.py` | Pending |
| TASK-006 | Thêm các env vars tương ứng vào `.env.example` | Pending |

### Implementation Phase 2: TavilyClient Service

- GOAL-002: Tạo TavilyClient class để handle API communication

| Task ID | Description | Status |
|---------|-------------|--------|
| TASK-007 | Tạo thư mục `src/services/external/` nếu chưa có | Pending |
| TASK-008 | Tạo `src/services/external/__init__.py` | Pending |
| TASK-009 | Tạo `src/services/external/tavily_client.py` với class `TavilyClient` | Pending |
| TASK-010 | Implement `__init__()` với config injection | Pending |
| TASK-011 | Implement `async search(query: str, **options) -> dict` method | Pending |
| TASK-012 | Implement error handling với `TavilyApiError` exception | Pending |
| TASK-013 | Add logging cho API calls và responses | Pending |
| TASK-014 | Add timeout handling với aiohttp | Pending |
| TASK-015 | Add response validation | Pending |
| TASK-016 | Add `_is_configured() -> bool` helper method | Pending |

### Implementation Phase 3: TavilySearchTool Implementation

- GOAL-003: Tạo TavilySearchTool kế thừa BaseTool

| Task ID | Description | Status |
|---------|-------------|--------|
| TASK-017 | Tạo file `src/services/tools/implementations/tavily_search_tool.py` | Pending |
| TASK-018 | Implement class `TavilySearchTool(BaseTool)` | Pending |
| TASK-019 | Implement `name` property → `"web_search"` | Pending |
| TASK-020 | Implement `description` property (Vietnamese, giải thích cho LLM khi nào dùng) | Pending |
| TASK-021 | Implement `parameters_schema` property với JSON Schema | Pending |
| TASK-022 | Implement `__init__(self, tavily_client: TavilyClient)` | Pending |
| TASK-023 | Implement `async execute(query: str, search_depth: str = "basic", max_results: int = 5) -> str` | Pending |
| TASK-024 | Add validation cho parameters | Pending |
| TASK-025 | Add graceful handling khi API unavailable | Pending |
| TASK-026 | Format response thành human-readable string | Pending |
| TASK-027 | Add logging cho tool execution | Pending |
| TASK-028 | Add error handling với ToolExecutionError | Pending |

### Implementation Phase 4: Dependency Injection Setup

- GOAL-004: Tích hợp TavilyClient vào dependency injection system

| Task ID | Description | Status |
|---------|-------------|--------|
| TASK-029 | Đọc và hiểu `src/services/dependencies.py` | Pending |
| TASK-030 | Thêm `_init_tavily_client()` helper function | Pending |
| TASK-031 | Initialize TavilyClient trong `initialize_all()` | Pending |
| TASK-032 | Pass TavilyClient vào TavilySearchTool constructor | Pending |
| TASK-033 | Add null handling khi TAVILY_API_KEY not configured | Pending |

### Implementation Phase 5: Tool Registration & Discovery

- GOAL-005: Đảm bảo tool được auto-discover và register

| Task ID | Description | Status |
|---------|-------------|--------|
| TASK-034 | Import TavilySearchTool trong `src/services/tools/implementations/__init__.py` | Pending |
| TASK-035 | Add vào `__all__` list | Pending |
| TASK-036 | Verify ToolDiscovery auto-imports tool từ implementations directory | Pending |
| TASK-037 | Test tool registration trong ToolRegistry | Pending |
| TASK-038 | Verify tool schema được generate đúng (OpenAI và MCP format) | Pending |

### Implementation Phase 6: Testing & Validation

- GOAL-006: Test và validate tool functionality

| Task ID | Description | Status |
|---------|-------------|--------|
| TASK-039 | Tạo `tests/services/external/test_tavily_client.py` | Pending |
| TASK-040 | Tạo `tests/services/tools/test_tavily_search_tool.py` | Pending |
| TASK-041 | Write unit test cho TavilyClient.search() | Pending |
| TASK-042 | Write unit test cho TavilySearchTool.execute() | Pending |
| TASK-043 | Write integration test với mock API | Pending |
| TASK-044 | Write test cho error scenarios (API unavailable, timeout, invalid key) | Pending |
| TASK-045 | Manual test với real Tavily API | Pending |
| TASK-046 | Test graceful degradation khi API key missing | Pending |
| TASK-047 | Test với Discord bot end-to-end | Pending |

### Implementation Phase 7: Documentation

- GOAL-007: Update documentation

| Task ID | Description | Status |
|---------|-------------|--------|
| TASK-048 | Update `README.MD` với Tavily setup instructions | Pending |
| TASK-049 | Add docstrings cho TavilyClient class và methods | Pending |
| TASK-050 | Add docstrings cho TavilySearchTool | Pending |
| TASK-051 | Update `.env.example` với comments giải thích | Pending |
| TASK-052 | Add tool usage examples trong documentation | Pending |

## 3. Alternatives

| Alt ID | Description | Pros | Cons | Decision |
|--------|-------------|------|------|----------|
| ALT-001 | Dùng SerpAPI thay vì Tavily | Established, nhiều features | Không chuyên cho AI agents, rate limits khắt khe | ❌ Not selected |
| ALT-002 | Dùng Google Custom Search API | Direct Google results | Requires setup, quota limits, not AI-optimized | ❌ Not selected |
| ALT-003 | Dùng DuckDuckGo Instant Answer API | Free, no API key | Limited results, not full web search | ❌ Not selected |
| ALT-004 | Implement web scraper trực tiếp | No API dependency | Complex, fragile, potential legal issues | ❌ Not selected |
| ALT-005 | Tavily API | AI-optimized, simple API, includes answer generation | Requires API key, usage limits | ✅ Selected |

## 4. Dependencies

| Dep ID | Type | Description | Status |
|--------|------|-------------|--------|
| DEP-001 | External | `aiohttp` - Already in requirements.txt | ✅ Available |
| DEP-002 | External | Tavily API - Requires account at app.tavily.com | ⏳ Pending |
| DEP-003 | Internal | `BaseTool` from `src/services/tools/base_tool.py` | ✅ Available |
| DEP-004 | Internal | `Config` from `src/config/settings.py` | ✅ Available |
| DEP-005 | Internal | `ToolDiscovery` auto-discovery system | ✅ Available |
| DEP-006 | API | Tavily API Key - Get from https://app.tavily.com/home | ⏳ Pending |

## 5. Files

| File ID | Path | Description | Status |
|---------|------|-------------|--------|
| FILE-001 | `src/services/external/__init__.py` | Package init | New |
| FILE-002 | `src/services/external/tavily_client.py` | Tavily API client | New |
| FILE-003 | `src/services/tools/implementations/tavily_search_tool.py` | MCP Tool implementation | New |
| FILE-004 | `tests/services/external/test_tavily_client.py` | Unit tests for client | New |
| FILE-005 | `tests/services/tools/test_tavily_search_tool.py` | Unit tests for tool | New |
| FILE-006 | `src/config/settings.py` | Add Tavily config vars | Modified |
| FILE-007 | `.env.example` | Add Tavily env vars | Modified |
| FILE-008 | `src/services/dependencies.py` | Add TavilyClient initialization | Modified |
| FILE-009 | `src/services/tools/implementations/__init__.py` | Import TavilySearchTool | Modified |
| FILE-010 | `README.MD` | Add Tavily setup documentation | Modified |

## 6. Testing

| Test ID | Description | Type | Status |
|---------|-------------|------|--------|
| TEST-001 | TavilyClient initialization với valid config | Unit | Pending |
| TEST-002 | TavilyClient initialization với missing config | Unit | Pending |
| TEST-003 | TavilyClient.search() returns results | Integration | Pending |
| TEST-004 | TavilyClient.search() handles timeout | Integration | Pending |
| TEST-005 | TavilyClient.search() handles API error | Integration | Pending |
| TEST-006 | TavilySearchTool.name returns "web_search" | Unit | Pending |
| TEST-007 | TavilySearchTool.description is Vietnamese | Unit | Pending |
| TEST-008 | TavilySearchTool.parameters_schema valid JSON Schema | Unit | Pending |
| TEST-009 | TavilySearchTool.execute() returns formatted results | Integration | Pending |
| TEST-010 | TavilySearchTool.execute() handles missing query | Unit | Pending |
| TEST-011 | TavilySearchTool.execute() handles API unavailable | Integration | Pending |
| TEST-012 | Tool auto-discovery registers TavilySearchTool | Integration | Pending |
| TEST-013 | End-to-end with Discord bot | E2E | Pending |
| TEST-014 | Tool works with MCP protocol | Integration | Pending |

## 7. Risks & Assumptions

| Risk ID | Description | Probability | Impact | Mitigation |
|---------|-------------|--------------|--------|------------|
| RISK-001 | Tavily API rate limits | Medium | Medium | Add configurable max_results, implement caching |
| RISK-002 | API key exposed in logs | Low | High | Never log API key, use environment variables |
| RISK-003 | API unavailable | Medium | Low | Graceful degradation, return friendly message |
| RISK-004 | Large response payloads | Low | Medium | Limit max_results, truncate response if needed |
| RISK-005 | Dependency injection complexity | Low | Medium | Follow existing patterns, test thoroughly |
| RISK-006 | Tool schema incompatible with LLM | Low | High | Follow OpenAI/MCP schema format strictly |

| Assumption ID | Description |
|---------------|-------------|
| ASSUMPTION-001 | Tavily API maintains backward compatibility |
| ASSUMPTION-002 | aiohttp handles HTTPS correctly without additional config |
| ASSUMPTION-003 | ToolDiscovery system auto-imports from implementations directory |
| ASSUMPTION-004 | Bot has internet access for API calls |
| ASSUMPTION-005 | User will provide Tavily API key from app.tavily.com |
| ASSUMPTION-006 | Existing tool infrastructure supports async execution |

## 8. Related Specifications / Further Reading

- [Tavily API Documentation](https://docs.tavily.com/)
- [Tavily API Reference](https://docs.tavily.com/api-reference/search)
- [BaseTool Implementation](src/services/tools/base_tool.py)
- [SearchMemoryTool Example](src/services/tools/implementations/search_memory_tool.py)
- [Tool Discovery System](src/services/tools/tool_discovery.py)
- [Dependency Injection](src/services/dependencies.py)
- [OpenAI Function Calling](https://platform.openai.com/docs/guides/function-calling)
- [MCP Protocol Specification](https://modelcontextprotocol.io/)