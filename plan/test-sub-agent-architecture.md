---
goal: Test Sub-Agent (Evernight) + Native Tools architecture with unit, integration, and E2E tests
version: "1.0"
date_created: "2026-04-25"
status: Planned
tags:
  - testing
  - sub-agent
  - evernight
  - wiki
  - queue
---

# Plan: Test Sub-Agent Architecture

## Overview

Comprehensive testing plan for the newly implemented Sub-Agent (Evernight) + Native Tools architecture.

**Test Categories:**
1. Unit Tests - Isolated component testing with mocks
2. Integration Tests - Component interaction testing
3. E2E Tests - Full flow simulation
4. Manual Tests - Discord bot scenarios

---

## Test Structure

```
tests/
├── conftest.py                    # Global fixtures (Redis, Qdrant, LLM mocks)
├── fixtures/
│   ├── redis_fixtures.py          # Redis mock fixtures
│   ├── qdrant_fixtures.py         # Qdrant mock fixtures
│   ├── llm_fixtures.py            # LLM response mocks
│   └── snapshot_fixtures.py       # T1 snapshot sample data
│
├── unit/
│   ├── wiki_page_test.py          # WikiPagePayload model tests
│   ├── wiki_storage_test.py       # WikiStorage tests (mock Qdrant)
│   ├── wiki_merge_test.py         # WikiMergeService tests (mock LLM)
│   ├── overflow_queue_test.py     # OverflowQueue tests (mock Redis)
│   ├── evernight_agent_test.py    # EvernightAgent tests
│   ├── nightly_trigger_test.py    # NightlyTrigger tests
│   └── spawner_test.py            # EvernightSpawner tests
│
├── integration/
│   ├── memory_manager_queue_test.py    # MemoryManager → Queue flow
│   ├── evernight_storage_test.py       # Agent → WikiStorage → Qdrant
│   ├── nightly_queue_test.py           # Nightly → Queue → Spawner
│   ├── overflow_trigger_test.py        # T1 overflow → Queue push
│
└── e2e/
    ├── chat_overflow_consolidate_test.py    # Full chat → Wiki flow
    └── nightly_consolidate_test.py          # Nightly wake → consolidate
```

---

## Phase 1: Test Infrastructure

### TASK-001: Create pytest.ini
**File:** `pytest.ini`
**Content:**
```ini
[pytest]
testpaths = tests
python_files = *_test.py
python_classes = Test*
python_functions = test_*
asyncio_mode = auto
markers =
    unit: Unit tests (isolated components)
    integration: Integration tests (component interactions)
    e2e: End-to-end tests (full flows)
    slow: Slow tests (skip with -m "not slow")
```

### TASK-002: Create Global conftest.py
**File:** `tests/conftest.py`
**Fixtures:**
- `mock_redis` - Redis mock with async support
- `mock_qdrant` - Qdrant client mock
- `mock_llm` - LLM service mock with preset responses
- `mock_embedding` - Embedding service mock

### TASK-003: Create Redis Fixtures
**File:** `tests/fixtures/redis_fixtures.py`
**Fixtures:**
- `redis_client` - Real Redis for integration (optional) or fakeredis
- `redis_storage` - Mock RedisStorage

### TASK-004: Create Qdrant Fixtures
**File:** `tests/fixtures/qdrant_fixtures.py`
**Fixtures:**
- `qdrant_client` - Mock AsyncQdrantClient
- `wiki_storage` - WikiStorage with mock client

### TASK-005: Create LLM Fixtures
**File:** `tests/fixtures/llm_fixtures.py`
**Fixtures:**
- `llm_client` - Mock LLM with canned responses
- `topic_extraction_response` - Sample LLM response for topic extraction
- `merge_response` - Sample LLM response for wiki merge

### TASK-006: Create Snapshot Fixtures
**File:** `tests/fixtures/snapshot_fixtures.py`
**Fixtures:**
- `sample_snapshot` - Sample T1 messages list
- `sample_wiki_page` - Sample WikiPagePayload

---

## Phase 2: Unit Tests - WikiPagePayload

### TASK-007: Test WikiPagePayload Model
**File:** `tests/unit/wiki_page_test.py`

| Test Case | Description |
|-----------|-------------|
| `test_page_id_generation` | Verify deterministic hash for same user+topic |
| `test_page_id_uniqueness` | Different topics produce different IDs |
| `test_serialization` | model_dump() produces valid JSON |
| `test_deserialization` | model_validate() from dict works |
| `test_relevance_calculation` | calculate_relevance() decay formula |
| `test_relevance_access_boost` | More access_count = higher relevance |
| `test_ttl_by_importance` | Importance mapping to TTL days |

**Mock Strategy:** No mocks needed (pure data model)

---

## Phase 3: Unit Tests - WikiStorage

### TASK-008: Test WikiStorage
**File:** `tests/unit/wiki_storage_test.py`

| Test Case | Description |
|-----------|-------------|
| `test_initialize_collection` | Collection created if not exists |
| `test_lookup_by_page_id_found` | Returns WikiPage when exists |
| `test_lookup_by_page_id_not_found` | Returns None when not exists |
| `test_upsert_page_success` | Page stored with embedding |
| `test_upsert_page_no_embedding` | Returns False without embedding |
| `test_search_similar_filters_user` | Only returns pages for correct user |
| `test_search_similar_relevance_filter` | Filters by min_relevance threshold |
| `test_refresh_access` | Updates last_accessed, access_count |
| `test_delete_page` | Page removed from collection |

**Mock Strategy:** Mock AsyncQdrantClient, use fakeredis or memory Qdrant

---

## Phase 4: Unit Tests - WikiMergeService

### TASK-009: Test WikiMergeService
**File:** `tests/unit/wiki_merge_test.py`

| Test Case | Description |
|-----------|-------------|
| `test_merge_mutable_replace` | Preferences replaced (rating 9→8) |
| `test_merge_accumulative_append` | Events combined (ep 1-6 + ep 7-13) |
| `test_merge_history_log` | Changes added to history_log |
| `test_merge_llm_error` | Returns None on LLM failure |
| `test_create_new_page` | New page created with correct fields |
| `test_calculate_ttl` | TTL mapped from importance |

**Mock Strategy:** Mock LLM client with preset JSON responses

---

## Phase 5: Unit Tests - OverflowQueue

### TASK-010: Test OverflowQueue
**File:** `tests/unit/overflow_queue_test.py`

| Test Case | Description |
|-----------|-------------|
| `test_push_to_queue` | Item added to Redis LIST |
| `test_pop_from_queue` | Item retrieved and removed |
| `test_pop_empty_queue` | Returns None when empty |
| `test_checkpoint_save` | Status saved to Redis HASH |
| `test_checkpoint_get` | Checkpoint retrieved |
| `test_checkpoint_clear` | Checkpoint removed |
| `test_queue_length` | LLEN returns count |

**Mock Strategy:** Use fakeredis or mock redis.asyncio.Redis

---

## Phase 6: Unit Tests - EvernightAgent

### TASK-011: Test EvernightAgent
**File:** `tests/unit/evernight_agent_test.py`

| Test Case | Description |
|-----------|-------------|
| `test_consolidate_no_topics` | Returns True when no topics found |
| `test_consolidate_single_topic` | One topic extracted and stored |
| `test_consolidate_multiple_topics` | Multiple topics processed |
| `test_consolidate_existing_page_merge` | Existing page merged instead of new |
| `test_consolidate_embedding_failure` | Handles embedding service failure |
| `test_extract_topics_json_parse` | LLM response parsed correctly |
| `test_extract_topics_empty_response` | Empty array handled |
| `test_format_snapshot` | Messages formatted for LLM |

**Mock Strategy:** Mock WikiStorage, WikiMergeService, LLM, Embedding

---

## Phase 7: Unit Tests - NightlyTrigger

### TASK-012: Test NightlyTrigger
**File:** `tests/unit/nightly_trigger_test.py`

| Test Case | Description |
|-----------|-------------|
| `test_trigger_at_hour` | Trigger fires at configured hour |
| `test_trigger_not_at_hour` | No trigger outside hour |
| `test_trigger_now` | Manual trigger works |
| `test_stop_trigger` | Loop stops on stop() call |
| `test_scan_users_empty` | Handles empty T1 |

**Mock Strategy:** Mock OverflowQueue, EvernightSpawner, asyncio.sleep

---

## Phase 8: Unit Tests - EvernightSpawner

### TASK-013: Test EvernightSpawner
**File:** `tests/unit/spawner_test.py`

| Test Case | Description |
|-----------|-------------|
| `test_spawn_for_user` | Task created for user |
| `test_spawn_duplicate_user` | Handles duplicate spawn request |
| `test_process_queue` | All queue items processed |
| `test_run_consolidation_success` | Checkpoint cleared on success |
| `test_run_consolidation_failure` | Checkpoint saved on failure |
| `test_wait_all_complete` | All tasks finish before return |

**Mock Strategy:** Mock EvernightAgent, OverflowQueue

---

## Phase 9: Integration Tests

### TASK-014: Test MemoryManager → Queue Flow
**File:** `tests/integration/memory_manager_queue_test.py`

| Test Case | Description |
|-----------|-------------|
| `test_overflow_pushes_to_queue` | TOKEN_LIMIT_REACHED → queue.push called |
| `test_overflow_spawns_task` | asyncio.create_task called |
| `test_overflow_cleanup_immediate` | T1 cleanup happens immediately |

**Mock Strategy:** Mock Queue, Spawner, verify method calls

### TASK-015: Test Evernight → Storage → Qdrant
**File:** `tests/integration/evernight_storage_test.py`

| Test Case | Description |
|-----------|-------------|
| `test_full_consolidation_flow` | Snapshot → topics → embed → upsert |
| `test_page_persisted_to_qdrant` | Verify Qdrant contains page |

**Mock Strategy:** Real Qdrant (local) or thorough mock

### TASK-016: Test Nightly → Queue → Spawner
**File:** `tests/integration/nightly_queue_test.py`

| Test Case | Description |
|-----------|-------------|
| `test_nightly_pushes_to_queue` | Users queued for consolidation |
| `test_nightly_spawns_tasks` | Tasks spawned for each user |

**Mock Strategy:** Mock all components, verify interactions

### TASK-017: Test T1 Overflow Trigger
**File:** `tests/integration/overflow_trigger_test.py`

| Test Case | Description |
|-----------|-------------|
| `test_token_limit_event_emitted` | 2000 tokens → event emitted |
| `test_event_handler_receives_snapshot` | Handler receives snapshot data |

**Mock Strategy:** Real ActiveMemoryService with mock storage

---

## Phase 10: E2E Tests

### TASK-018: Test Full Chat → Consolidation Flow
**File:** `tests/e2e/chat_overflow_consolidate_test.py`

**Flow:**
1. Add messages to T1 until overflow
2. Verify queue receives snapshot
3. Verify Evernight spawns
4. Verify WikiPage in Qdrant
5. Verify T1 cleaned

**Mock Strategy:** Real components where possible, mock external services

### TASK-019: Test Nightly Consolidation
**File:** `tests/e2e/nightly_consolidate_test.py`

**Flow:**
1. Add messages to T1 (below overflow)
2. Trigger nightly manually
3. Verify T1 scanned
4. Verify consolidation happens
5. Verify T1 cleared

**Mock Strategy:** Mock time, use real components

---

## Phase 11: Manual/Simulation Tests

### TASK-020: Discord Bot Simulation

**Scenarios:**

| Scenario | Steps | Expected Result |
|----------|-------|-----------------|
| **Chat Overflow** | 1. Send many messages<br>2. Wait for 2000 tokens<br>3. Check Qdrant | WikiPage created |
| **SearchMemory** | 1. Create WikiPages<br>2. Call SearchMemoryTool<br>3. Query topic | Results returned |
| **UpdateProfile** | 1. Call UpdateProfileTool<br>2. Check IDENTITY.md | Profile updated |
| **Nightly Wake** | 1. Set trigger hour<br>2. Wait or trigger manually<br>3. Check Qdrant | Remaining T1 consolidated |

---

## Test Execution Order

```
Phase 1 (Infrastructure) → Phases 2-8 (Unit Tests) → Phase 9 (Integration) → Phase 10 (E2E) → Phase 11 (Manual)

Unit Tests can run in parallel after infrastructure setup.
Integration Tests depend on Unit Tests passing.
E2E Tests depend on Integration Tests passing.
```

---

## Task Checklist

### Phase 1: Infrastructure (6 tasks)
- [ ] TASK-001: Create pytest.ini
- [ ] TASK-002: Create conftest.py
- [ ] TASK-003: Create redis_fixtures.py
- [ ] TASK-004: Create qdrant_fixtures.py
- [ ] TASK-005: Create llm_fixtures.py
- [ ] TASK-006: Create snapshot_fixtures.py

### Phase 2: WikiPagePayload (7 tests)
- [ ] TASK-007: Test WikiPagePayload model

### Phase 3: WikiStorage (9 tests)
- [ ] TASK-008: Test WikiStorage

### Phase 4: WikiMerge (6 tests)
- [ ] TASK-009: Test WikiMergeService

### Phase 5: OverflowQueue (7 tests)
- [ ] TASK-010: Test OverflowQueue

### Phase 6: EvernightAgent (8 tests)
- [ ] TASK-011: Test EvernightAgent

### Phase 7: NightlyTrigger (5 tests)
- [ ] TASK-012: Test NightlyTrigger

### Phase 8: EvernightSpawner (6 tests)
- [ ] TASK-013: Test EvernightSpawner

### Phase 9: Integration (4 tests)
- [ ] TASK-014: Test MemoryManager → Queue
- [ ] TASK-015: Test Evernight → Storage
- [ ] TASK-016: Test Nightly → Queue → Spawner
- [ ] TASK-017: Test T1 Overflow Trigger

### Phase 10: E2E (2 tests)
- [ ] TASK-018: Test Full Chat → Consolidation
- [ ] TASK-019: Test Nightly Consolidation

### Phase 11: Manual (1 scenario set)
- [ ] TASK-020: Discord Bot Simulation

---

## Summary

| Metric | Count |
|--------|-------|
| Test Phases | 11 |
| Total Tasks | 20 |
| Unit Test Files | 7 |
| Integration Test Files | 4 |
| E2E Test Files | 2 |
| Fixture Files | 4 |
| New Files to Create | ~20 |

---

## Risks

| Risk | Mitigation |
|------|------------|
| Redis/Qdrant not available | Use mocks/fakeredis for unit tests |
| LLM responses unpredictable | Use preset JSON fixtures |
| Async tests timing issues | Use pytest-asyncio with proper fixtures |

---

## Next Action

**Start Phase 1: Test Infrastructure**
- Create pytest.ini
- Create conftest.py with global fixtures
- Create fixture files for Redis, Qdrant, LLM mocks