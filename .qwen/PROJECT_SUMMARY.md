# Project Summary

## Overall Goal
Implement comprehensive test suite for Sub-Agent (Evernight) + Native Tools architecture - a Discord bot memory system with T1 overflow → T2 Wiki consolidation → T3 Core Memory flow.

## Key Knowledge

### Architecture
- **Bay (Main Agent) + Evernight (Sub-Agent)** in single process, no Redis Pub/Sub
- **T2 Approach**: WikiPage (Upsert) with Vectorized Wiki Architecture, not TopicChunks
- **T3 Update**: LLM merge into IDENTITY.md via UpdateProfileTool MCP
- **Queue**: Redis List for persistent overflow snapshots
- **Error Handling**: Checkpoint into Redis for Evernight recovery
- **Dual Trigger**: Token Overflow (MAX_WORKING_TOKENS=2000) + Nightly Cron (2 AM)
- **SOLID/SRP**: Each class has one responsibility

### Test Infrastructure
- **Environment**: Conda `discord_bot` (Python 3.14.3)
- **Test Framework**: pytest with pytest-asyncio
- **Services**: Docker containers `be_bay_redis`, `be_bay_qdrant`, `be_bay_bot`
- **Run Command**: `conda run -n discord_bot --cwd /home/flowerf/Projects/discord-bot-v1 pytest tests/ -v --tb=short`

### Source Code Fixes Applied
1. **Circular Import** (`src/services/dependencies.py`) - Moved Evernight imports to lazy imports inside `initialize()`
2. **Prompt Format** (`src/agents/evernight/services/wiki_merge.py`) - Escaped JSON curly braces with `{{` and `}}`
3. **WikiMergeService Init** - Requires `llm_client` positional argument
4. **LLMResponse Mock** (`tests/manual/test_overflow_flow.py`) - Fixed `tokens_used` → `input_tokens/output_tokens`
5. **Page ID UUID Format** (`src/agents/shared/models/wiki_page.py`) - Changed hex hash to UUID format for Qdrant compatibility

### Mock Fixtures Strategy
- `mock_redis`: Uses `set_return_value()` helper for test override + internal `_queue` storage
- `mock_qdrant_client`: Returns actual string names for collections (not MagicMock)
- `mock_llm_client`: Uses `add_response()` method for preset responses
- `sample_points`: Factory fixture for Qdrant points

## Recent Actions

### Test Files Created

| Category | Files | Tests | Status |
|----------|-------|-------|--------|
| Unit | 5 files | 63 | ✅ PASSED |
| Integration | 4 files | 36 | ✅ PASSED |
| E2E | 2 files | 17 | ✅ PASSED |
| Manual | 5 scripts | - | ✅ All Working |

### Unit Tests (63 tests)
- `wiki_page_test.py` - WikiPagePayload model, page_id generation, relevance calculation
- `overflow_queue_test.py` - Redis queue operations, checkpoint
- `wiki_storage_test.py` - Qdrant CRUD, search, initialization
- `wiki_merge_test.py` - LLM merge logic, TTL calculation
- `fixtures_verification_test.py` - Fixture validation

### Integration Tests (36 tests)
- `memory_manager_queue_test.py` - T1 overflow → Queue → Spawner
- `evernight_storage_test.py` - Evernight → WikiStorage → Qdrant
- `nightly_trigger_test.py` - Scheduled trigger lifecycle
- `overflow_trigger_test.py` - Token threshold trigger

### E2E Tests (17 tests)
- `chat_overflow_consolidate_test.py` - Full chat → Wiki flow
- `nightly_consolidate_test.py` - Nightly wake → consolidate

### Manual Scripts (5 scripts)
- `check_services.py` - Service health check ✅
- `test_overflow_flow.py` - T1 overflow → Wiki consolidation ✅ (Fixed UUID format)
- `test_nightly_trigger.py` - Nightly consolidation ✅
- `test_search_wiki.py` - WikiPage search ✅ (Requires conda env for torch)
- `README.md` - Usage guide

## Current Status

### [COMPLETED] Test Implementation + Bug Fixes
1. ✅ pytest.ini configuration
2. ✅ Global fixtures (conftest.py)
3. ✅ Unit tests (63 tests)
4. ✅ Integration tests (36 tests)
5. ✅ E2E tests (17 tests)
6. ✅ Manual test scripts (5 scripts)
7. ✅ Services running (Redis, Qdrant, Bot)
8. ✅ All manual tests passing
9. ✅ Fixed Qdrant UUID format for page_id
10. ✅ Fixed LLMResponse mock parameter

### [TODO] Future Work
- Test with real Discord bot connection
- Implement SearchMemoryTool WikiPages integration
- Add UpdateProfileTool LLM merge logic for T3
- Configure Evernight with smaller/cheaper model if desired

### Test Structure
```
tests/
├── conftest.py                 # Global fixtures
├── unit/                       # 63 tests
├── integration/                # 36 tests
├── e2e/                        # 17 tests
└── manual/                     # 5 scripts
```

### Key Commands
```bash
# Run all automated tests (118 tests)
conda run -n discord_bot --cwd /home/flowerf/Projects/discord-bot-v1 pytest tests/ -v --tb=short --ignore=tests/manual

# Check services
python tests/manual/check_services.py

# Test overflow (creates WikiPages in Qdrant)
python tests/manual/test_overflow_flow.py --user-id test_user_123 --cleanup

# Test nightly consolidation
python tests/manual/test_nightly_trigger.py --cleanup

# Verify WikiPages in Qdrant
curl -s http://localhost:6333/collections/wiki_pages/points/scroll \
  -X POST -H "Content-Type: application/json" \
  -d '{"limit": 10, "with_payload": true}' | python -m json.tool
```

---

## Summary Metadata
**Update time**: 2026-04-25T16:30:00Z