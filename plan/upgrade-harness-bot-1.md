---
goal: Chuyển đổi Discord Bot thành Harness Bot - Hỗ trợ Reasoning Models và Native Function Calling
version: 1.0
date_created: 2026-04-13
last_updated: 2026-04-13
owner: Flowerf
status: 'In progress'
tags: ['upgrade', 'architecture', 'reasoning-models', 'native-tool-calling', 'discord']
---

# Introduction

![Status: In progress](https://img.shields.io/badge/status-In_progress-yellow)

Plan này chuyển đổi Discord LLM Bot thành **Harness Bot** - một bot có khả năng:
1. **Hỗ trợ Reasoning Models**: DeepSeek R1, Qwen thinking models với `reasoning_content` field
2. **Native Function Calling**: Sử dụng API tool calling thay vì regex parsing
3. **Tăng cường Token Limits**: 2000 tokens cho reasoning models (thinking + final answer)
4. **Debug Logging**: Chi tiết hơn để debug reasoning models

Branch hiện tại: `Harness_discord_v1` - đang làm dở với các thay đổi chưa commit.

## 1. Requirements & Constraints

- **REQ-001**: Bot phải hỗ trợ reasoning models (DeepSeek R1, Qwen thinking) với field `reasoning_content`
- **REQ-002**: Native function calling qua API thay vì regex parsing
- **REQ-003**: Token limit tăng từ 100 → 2000 cho reasoning models
- **REQ-004**: Timeout tool execution tăng từ 30s → 60s
- **REQ-005**: Debug logging chi tiết cho reasoning models
- **REQ-006**: LM Studio Service phải detect và xử lý `reasoning_content` field
- **SEC-001**: Không log sensitive data (API keys, user tokens)
- **CON-001**: Phải maintain backward compatibility với non-reasoning models
- **CON-002**: Gemini API format khác với OpenAI format - cần xử lý riêng
- **GUD-001**: Follow existing Service-Repository pattern
- **PAT-001**: Use `_detect_llm_type()` để format messages đúng chuẩn API

## 2. Implementation Steps

### Implementation Phase 1: Core Settings & Configuration

- GOAL-001: Cập nhật settings.py và config cho reasoning models

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Update `LLM_MODEL` default từ `gemini-1.5-flash` → `gemini-2.5-flash` trong `src/config/settings.py` | ✅ | 2026-04-13 |
| TASK-002 | Update `LLM_MAX_TOKENS` từ 100 → 2000 với comment explaining reasoning models | ✅ | 2026-04-13 |
| TASK-003 | Update `TOOL_EXECUTION_TIMEOUT` từ 30 → 60 seconds trong `src/services/chat_coordinator.py` | ✅ | 2026-04-13 |

### Implementation Phase 2: LM Studio Service - Reasoning Model Support

- GOAL-002: Implement reasoning_content handling trong LM Studio Service

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-004 | Add debug logging cho raw response keys trong `lm_studio_service.py` | ✅ | 2026-04-13 |
| TASK-005 | Add debug logging cho choice keys và message keys | ✅ | 2026-04-13 |
| TASK-006 | Add debug logging cho content preview (500 chars) | ✅ | 2026-04-13 |
| TASK-007 | Check và log `reasoning_content` field (DeepSeek R1 format) | ✅ | 2026-04-13 |
| TASK-008 | Implement fallback: nếu `content` empty, use `reasoning_content` | ✅ | 2026-04-13 |
| TASK-009 | Add info logging cho detected reasoning_content | ✅ | 2026-04-13 |
| TASK-010 | Add final content preview logging (200 chars) | ✅ | 2026-04-13 |

### Implementation Phase 3: Chat Coordinator - Native Tool Calling

- GOAL-003: Enhance ChatCoordinator với native function calling support

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-011 | Verify `_detect_llm_type()` method exists và hoạt động đúng | ✅ | (existing) |
| TASK-012 | Verify `_format_tool_call_message()` handles Gemini vs OpenAI format | ✅ | (existing) |
| TASK-013 | Verify `_format_tool_result_message()` format đúng cho từng LLM type | ✅ | (existing) |
| TASK-014 | Test native tool calling với Gemini API | | |
| TASK-015 | Test native tool calling với LM Studio (OpenAI format) | | |

### Implementation Phase 4: Memory System Updates

- GOAL-004: Cập nhật memory files và identity

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-016 | Update `memories/IDENTITY.md` - thêm note về tính cách ngắn gọn | ✅ | 2026-04-13 |
| TASK-017 | Update `memories/users/726302130318868500.md` - sửa tên từ Hoàng → Hòa | ✅ | 2026-04-13 |
| TASK-018 | Create `memories/INDEX.md` file (currently empty) | | |
| TASK-019 | Populate INDEX.md với structure overview của memory system | | |

### Implementation Phase 5: Testing & Validation

- GOAL-005: Test và validate harness bot functionality

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-020 | Test bot với Gemini 2.5 Flash (non-reasoning) | | |
| TASK-021 | Test bot với DeepSeek R1 via LM Studio (reasoning model) | | |
| TASK-022 | Test native tool calling với sample tools | | |
| TASK-023 | Verify backward compatibility với existing features | | |
| TASK-024 | Monitor token usage với reasoning models | | |

### Implementation Phase 6: Documentation & Cleanup

- GOAL-006: Update documentation và cleanup code

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-025 | Update `agent.md` với harness bot capabilities | | |
| TASK-026 | Update `README.MD` với reasoning models section | | |
| TASK-027 | Add `.env.example` entries cho reasoning model settings | | |
| TASK-028 | Remove debug logging sau khi testing complete (optional) | | |
| TASK-029 | Commit changes với proper message | | |

## 3. Alternatives

- **ALT-001**: Giữ nguyên regex parsing cho tool calling - **Không chọn** vì native API calling hiệu quả hơn, ít lỗi hơn
- **ALT-002**: Tạo riêng ReasoningModelService class - **Không chọn** vì tăng complexity, better to handle trong existing service
- **ALT-003**: Hard-code token limit 2000 - **Không chọn** vì dùng env var linh hoạt hơn cho different models

## 4. Dependencies

- **DEP-001**: `discord.py` - Discord bot framework
- **DEP-002**: `langsmith` - Tracing và monitoring
- **DEP-003**: LM Studio local server - Running reasoning models
- **DEP-004**: Gemini API - Google's LLM service
- **DEP-005**: Qwen3-Embedding-0.6B - Local embedding service

## 5. Files

| File ID | Path | Description | Status |
|---------|------|-------------|--------|
| FILE-001 | `src/config/settings.py` | Config settings, LLM_MODEL, LLM_MAX_TOKENS | Modified |
| FILE-002 | `src/services/chat_coordinator.py` | Main orchestrator, timeout settings | Modified |
| FILE-003 | `src/services/llm/lm_studio_service.py` | LM Studio service, reasoning_content handling | Modified |
| FILE-004 | `memories/IDENTITY.md` | Bot personality, character traits | Modified |
| FILE-005 | `memories/users/726302130318868500.md` | User profile storage | Modified |
| FILE-006 | `memories/INDEX.md` | Memory system index (new file) | New |
| FILE-007 | `data/bot_channels.json` | Bot channel whitelist | Modified |
| FILE-008 | `agent.md` | AI Agent guide documentation | To Update |
| FILE-009 | `README.MD` | Project documentation | To Update |

## 6. Testing

| Test ID | Description | Type | Status |
|---------|-------------|------|--------|
| TEST-001 | Test Gemini 2.5 Flash response generation | Integration | Pending |
| TEST-002 | Test DeepSeek R1 reasoning_content extraction | Integration | Pending |
| TEST-003 | Test native tool calling với Gemini | Integration | Pending |
| TEST-004 | Test native tool calling với LM Studio | Integration | Pending |
| TEST-005 | Test token limit enforcement | Unit | Pending |
| TEST-006 | Test backward compatibility với Qwen service | Integration | Pending |
| TEST-007 | Test memory system vẫn hoạt động đúng | Integration | Pending |

## 7. Risks & Assumptions

| Risk ID | Description | Mitigation |
|---------|-------------|------------|
| RISK-001 | Reasoning models có thể trả về empty content | Fallback to reasoning_content field |
| RISK-002 | Gemini API format khác với OpenAI | Use `_detect_llm_type()` và format accordingly |
| RISK-003 | Token usage cao hơn với reasoning models | Monitor và adjust MAX_TOKENS if needed |
| RISK-004 | Debug logging có thể expose sensitive data | Only log previews, not full content |

| Assumption ID | Description |
|---------------|-------------|
| ASSUMPTION-001 | LM Studio hỗ trợ OpenAI-compatible API với reasoning_content |
| ASSUMPTION-002 | Gemini 2.5 Flash không có reasoning_content field |
| ASSUMPTION-003 | Existing memory system không cần thay đổi |
| ASSUMPTION-004 | Tool Manager đã implement native tool calling |

## 8. Related Specifications / Further Reading

- [Native Function Calling Implementation](src/services/chat_coordinator.py)
- [LM Studio Service Documentation](src/services/llm/lm_studio_service.py)
- [Three-Tier Memory System](memories/)
- [DeepSeek R1 API Documentation](https://api-docs.deepseek.com/)
- [OpenAI Function Calling Guide](https://platform.openai.com/docs/guides/function-calling)