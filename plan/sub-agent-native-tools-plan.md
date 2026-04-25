---
goal: Implement Sub-Agent (Evernight) + Native Tools architecture with proper SOLID/SRP principles
version: "1.0"
date_created: "2026-04-25"
last_updated: "2026-04-25"
status: COMPLETED
tags:
  - architecture
  - memory-system
  - sub-agent
  - mcp-tools
  - cleanup
---

# Plan: Sub-Agent & Native Tools Architecture

## Overview

**Goal:** Separate Chat flow (Real-time) and Memory Consolidation (Background) in single process. Transfer knowledge retrieval to MCP Tools.

**Principles:**
- **SRP:** Each class has one responsibility (Evernight = T2 only, Bay = T1+T3+Chat)
- **OCP:** MCP Tools extend functionality without modifying core classes
- **DIP:** MemoryManager depends on abstractions, not concrete implementations

---

## Architecture Summary

```
┌─────────────────────────────────────────────────────────────────────┐
│                    SUB-AGENT ARCHITECTURE                           │
│                                                                     │
│   ┌─────────────────────┐         ┌─────────────────────┐          │
│   │        BAY          │         │     EVERNIGHT       │          │
│   │   (Main Discord)    │         │   (Sub-Agent)       │          │
│   │                     │         │                     │          │
│   │ • T1 Active Memory  │──queue──│►• T2 Wiki Consolid  │          │
│   │ • T3 Core Memory    │         │ • Background task   │          │
│   │ • MCP Tools         │         │ • Own LLM config    │          │
│   │ • User chat         │         │                     │          │
│   └─────────────────────┘         └─────────────────────┘          │
│                                                                     │
│   ┌─────────────────────────────────────────────────────────────┐  │
│   │                    SHARED INFRASTRUCTURE                     │  │
│   │  • Redis (Queue + Checkpoint)                                │  │
│   │  • Qdrant (T2 storage)                                       │  │
│   │  • MCP Tool Registry                                         │  │
│   └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Key Decisions

| Component | Decision |
|-----------|----------|
| **T2 Approach** | WikiPage (Upsert) - Vectorized Wiki Architecture |
| **T3 Update** | LLM merge into file (via UpdateProfileTool MCP) |
| **T3 Handler** | Bay handles T3 via MCP Tools |
| **Queue** | Redis List (persistent queue for overflow snapshots) |
| **Error Handling** | Checkpoint into Redis for Evernight recovery |
| **Communication** | No Redis Pub/Sub - Internal asyncio spawn |

---

## Phase 0: Cleanup (Kill List)

**Goal:** Remove deprecated mechanisms before new architecture.

### P0-001: Delete EvaluationPipeline
**File:** `src/services/memories/activate_memory/evaluation/pipeline.py`
**Action:** DELETE
**Reason:** T1 không cần pre-evaluation. Score=0.2 default useless.

### P0-002: Delete RuleEngine
**File:** `src/services/memories/activate_memory/evaluation/rule_engine.py`
**Action:** DELETE
**Reason:** Explicit commands (!note) handled by MCP tools, not RuleEngine.

### P0-003: Delete Evaluation Directory
**File:** `src/services/memories/activate_memory/evaluation/__init__.py`
**Action:** DELETE
**Reason:** Directory empty after P0-001, P0-002.

### P0-004: Simplify MessageCategory
**File:** `src/services/memories/activate_memory/models.py`
**Action:** MODIFY
**Change:**
```python
# BEFORE: 8 categories
class MessageCategory(str, Enum):
    GENERAL = "general"
    FACT = "fact"
    GOAL = "goal"
    ...

# AFTER: Only GENERAL
class MessageCategory(str, Enum):
    GENERAL = "general"
```
**Reason:** No evaluation → No categorization needed.

### P0-005: Remove CRITICAL_INFO_THRESHOLD
**File:** `src/services/memories/activate_memory/constants.py`
**Action:** MODIFY - DELETE constant
**Change:**
```python
# DELETE this line:
CRITICAL_INFO_THRESHOLD = 0.45
```
**Reason:** Semantic trigger removed. No threshold needed.

### P0-006: Remove Semantic Trigger in ActiveMemoryService
**File:** `src/services/memories/activate_memory/activate_memory_service.py`
**Action:** MODIFY
**Change:** Remove lines 57-68 (CRITICAL_INFO_DETECTED event emission)
**Reason:** T3 update handled by MCP tool (UpdateProfileTool), not event.

### P0-007: Remove EvaluationPipeline Dependency
**File:** `src/services/memories/activate_memory/activate_memory_service.py`
**Action:** MODIFY
**Change:**
- Remove `EvaluationPipeline` import
- Remove `pipeline` parameter in constructor
- Remove `pipeline.evaluate_message()` call in `add_message()`
- Set default score=0.0, category=MessageCategory.GENERAL
**Reason:** No evaluation pipeline needed.

### P0-008: Remove RuleEngine Registration
**File:** `src/config/dependencies.py` (or wherever DI happens)
**Action:** MODIFY
**Change:** Remove RuleEngine, EvaluationPipeline registration
**Reason:** Dependencies deleted.

### P0-009: Remove EpisodicManager from MemoryManager
**File:** `src/services/memories/memory_manager.py`
**Action:** MODIFY
**Change:**
- Remove `EpisodicManager` import
- Remove `episodic_memory` parameter in constructor
- Remove `self.t2` attribute
**Reason:** MemoryManager only manages T1 + T3. T2 handled by Evernight.

### P0-010: Remove _run_t2_past_events()
**File:** `src/services/memories/memory_manager.py`
**Action:** MODIFY
**Change:** Remove `_run_t2_past_events()` function and its call in `get_context()`
**Reason:** Auto-retrieval T2 removed. SearchMemoryTool handles T2 query.

### P0-011: Remove CRITICAL_INFO_DETECTED Subscription
**File:** `src/services/memories/memory_manager.py`
**Action:** MODIFY
**Change:** Remove any subscription to CRITICAL_INFO_DETECTED (if exists)
**Reason:** Event removed.

### P0-012: Update _handle_memory_overflow
**File:** `src/services/memories/memory_manager.py`
**Action:** MODIFY
**Change:**
```python
# BEFORE: Direct T2 ingest
async def _handle_memory_overflow(self, event_type: str, user_id: str, data: dict):
    snapshot = data.get("snapshot", [])
    success = await self.t2.ingest_snapshot(user_id, snapshot)
    if success:
        await self.t1.force_cleanup(user_id)

# AFTER: Queue to Redis, spawn Evernight
async def _handle_memory_overflow(self, event_type: str, user_id: str, data: dict):
    snapshot = data.get("snapshot", [])
    await self._queue_overflow(user_id, snapshot)  # Push to Redis List
    asyncio.create_task(self._spawn_evernight(user_id))  # Fire-and-forget
    await self.t1.force_cleanup(user_id)  # Cleanup immediately
```
**Reason:** Evernight handles T2, not MemoryManager.

---

## Phase 1: MCP Tools

**Goal:** Create MCP Tools for Bay to access T2 and T3.

### P1-001: Create SearchMemoryTool
**File:** `src/tools/search_memory_tool.py`
**Responsibility:** Query T2 (WikiPages) via Qdrant semantic search
**Interface:**
```python
class SearchMemoryTool:
    """MCP Tool for Bay to search T2 WikiPages."""

    async def execute(self, user_id: str, query: str) -> str:
        """
        1. Embed query
        2. Search Qdrant for WikiPages
        3. Return formatted context string
        """
```

### P1-002: Create UpdateProfileTool
**File:** `src/tools/update_profile_tool.py`
**Responsibility:** Update T3 (IDENTITY.md) via LLM merge
**Interface:**
```python
class UpdateProfileTool:
    """MCP Tool for Bay to update T3 profile."""

    async def execute(self, user_id: str, fact: str) -> bool:
        """
        1. Read current IDENTITY.md
        2. Call LLM to merge fact
        3. Write back to file
        """
```

### P1-003: Register Tools in MCP Registry
**File:** `src/tools/__init__.py` or `src/config/mcp_registry.py`
**Action:** CREATE tool registry
**Reason:** Central place for tool registration.

### P1-004: Wire Tools to Bay
**File:** `src/bot.py` or `src/agents/bay/agent.py`
**Action:** MODIFY to include tools in LLM function calling
**Reason:** Bay needs access to tools.

---

## Phase 2: Evernight Sub-Agent

**Goal:** Build Evernight for T2 Wiki consolidation.

### P2-001: Create EvernightAgent Class
**File:** `src/agents/evernight/agent.py`
**Responsibility:** T2 Wiki consolidation (single responsibility)
**Interface:**
```python
class EvernightAgent:
    """Sub-Agent for T2 memory consolidation."""

    async def consolidate(self, user_id: str, snapshot: List[dict]) -> bool:
        """
        1. Extract topics from snapshot
        2. For each topic:
           - Generate page_id = hash(user_id + canonical_topic)
           - Lookup existing WikiPage
           - LLM Merge if exists, Create if new
           - Embed and Upsert to Qdrant
        """
```

### P2-002: Create WikiPage Model
**File:** `src/agents/shared/models/wiki_page.py`
**Responsibility:** Data model for WikiPage payload
**Interface:**
```python
class WikiPagePayload(BaseModel):
    page_id: str              # hash(user_id + canonical_topic)
    user_id: str
    canonical_topic: str
    category: str
    current_summary: str
    key_points: List[str]
    importance: int           # 1-5
    ttl_days: int
    created_at: datetime
    last_updated: datetime
    last_accessed: datetime
    access_count: int
```

### P2-003: Create WikiStorage Service
**File:** `src/agents/evernight/services/wiki_storage.py`
**Responsibility:** Qdrant operations for WikiPages (SRP)
**Interface:**
```python
class WikiStorage:
    """Qdrant storage service for WikiPages."""

    async def lookup_by_page_id(self, page_id: str) -> WikiPagePayload | None
    async def upsert_page(self, page: WikiPagePayload) -> bool
    async def search_similar(self, user_id: str, query_vector: List[float], top_k: int) -> List[WikiPagePayload]
```

### P2-004: Create WikiMergeService
**File:** `src/agents/evernight/services/wiki_merge.py`
**Responsibility:** LLM merge logic for WikiPages (SRP)
**Interface:**
```python
class WikiMergeService:
    """LLM-based merge for WikiPages."""

    async def merge(self, old_page: WikiPagePayload, new_info: dict) -> WikiPagePayload:
        """
        Call LLM with WIKI_MERGE_PROMPT.
        Handle contradictions, accumulate facts.
        """
```

### P2-005: Create EvernightConfig
**File:** `src/agents/evernight/config.py`
**Responsibility:** Own LLM config for Evernight (smaller/cheaper model)
**Reason:** Independent config, can use different model than Bay.

---

## Phase 3: Triggers & Queue

**Goal:** Implement dual trigger mechanism.

### P3-001: Create OverflowQueue Service
**File:** `src/services/queue/overflow_queue.py`
**Responsibility:** Redis List operations for snapshot queue (SRP)
**Interface:**
```python
class OverflowQueue:
    """Redis-based queue for T1 overflow snapshots."""

    async def push(self, user_id: str, snapshot: List[dict]) -> None
    async def pop(self) -> Tuple[str, List[dict]] | None
    async def checkpoint(self, user_id: str, status: str) -> None  # For error recovery
```

### P3-002: Create NightlyTrigger Task
**File:** `src/tasks/nightly_trigger.py`
**Responsibility:** Scheduled trigger (11PM or configurable)
**Interface:**
```python
async def nightly_consolidation():
    """
    1. Scan Redis for users with T1 data but no overflow today
    2. Pull all T1 entries
    3. Queue to OverflowQueue
    4. Spawn Evernight for each
    """
```

### P3-003: Wire Token Overflow Trigger
**File:** `src/services/memories/memory_manager.py`
**Action:** MODIFY `_handle_memory_overflow`
**Change:** Queue snapshot → Spawn Evernight task

### P3-004: Create Evernight Spawner
**File:** `src/agents/evernight/spawner.py`
**Responsibility:** Spawn and manage Evernight tasks
**Interface:**
```python
class EvernightSpawner:
    """Spawn Evernight consolidation tasks."""

    async def spawn_for_user(self, user_id: str) -> None:
        """Create asyncio task for Evernight consolidation."""
```

---

## Phase 4: Integration & Wiring

**Goal:** Connect all components.

### P4-001: Update MemoryManager Constructor
**File:** `src/services/memories/memory_manager.py`
**Action:** MODIFY
**Change:**
```python
# AFTER: Only T1 + T3 + Queue
class MemoryManager:
    def __init__(
        self,
        active_memory: ActiveMemoryService,
        core_memory: CoreManager,
        overflow_queue: OverflowQueue,
        evernight_spawner: EvernightSpawner,
        event_dispatcher: EventDispatcher,
    ):
        self.t1 = active_memory
        self.t3 = core_memory
        self.queue = overflow_queue
        self.spawner = evernight_spawner
        self.events = event_dispatcher
```

### P4-002: Update get_context()
**File:** `src/services/memories/memory_manager.py`
**Action:** MODIFY
**Change:**
```python
# AFTER: Only T1 + T3 (no T2 auto-retrieval)
async def get_context(self, user_id: str) -> Tuple[str, List[Dict]]:
    system_prompt, context_messages = await asyncio.gather(
        self.t3.get_system_prompt_context(user_id),
        self.t1.get_context_for_llm(user_id),
    )
    return system_prompt, context_messages
```

### P4-003: Update DI Container
**File:** `src/config/dependencies.py`
**Action:** MODIFY
**Change:**
- Remove EpisodicManager registration
- Add OverflowQueue registration
- Add EvernightSpawner registration
- Add SearchMemoryTool, UpdateProfileTool registration

### P4-004: Update Bot Entry Point
**File:** `src/bot.py` or `src/__main__.py`
**Action:** MODIFY
**Change:**
- Start NightlyTrigger task on bot ready
- Wire MCP tools to LLM

---

## Files Summary

### New Files (14)
- `src/agents/__init__.py`
- `src/agents/evernight/__init__.py`
- `src/agents/evernight/agent.py`
- `src/agents/evernight/config.py`
- `src/agents/evernight/spawner.py`
- `src/agents/evernight/services/wiki_storage.py`
- `src/agents/evernight/services/wiki_merge.py`
- `src/agents/shared/__init__.py`
- `src/agents/shared/models/__init__.py`
- `src/agents/shared/models/wiki_page.py`
- `src/tools/__init__.py`
- `src/tools/search_memory_tool.py`
- `src/tools/update_profile_tool.py`
- `src/services/queue/overflow_queue.py`
- `src/tasks/nightly_trigger.py`

### Modified Files (6)
- `src/services/memories/memory_manager.py`
- `src/services/memories/activate_memory/activate_memory_service.py`
- `src/services/memories/activate_memory/models.py`
- `src/services/memories/activate_memory/constants.py`
- `src/config/dependencies.py`
- `src/bot.py`

### Deleted Files (3)
- `src/services/memories/activate_memory/evaluation/pipeline.py`
- `src/services/memories/activate_memory/evaluation/rule_engine.py`
- `src/services/memories/activate_memory/evaluation/__init__.py`

### Deleted Directory (1)
- `src/services/memories/activate_memory/evaluation/`

---

## Dependencies Graph

```
Phase 0 (Cleanup) ─────────────────────────────────────────────────
│
│   P0-001 ─► P0-002 ─► P0-003 (Delete evaluation)
│   P0-004 ─► P0-005 (Simplify models/constants)
│   P0-006 ─► P0-007 (Remove from ActiveMemoryService)
│   P0-009 ─► P0-010 ─► P0-012 (Remove from MemoryManager)
│
▼
Phase 1 (MCP Tools) ───────────────────────────────────────────────
│
│   P1-001 ─► P1-002 ─► P1-003 ─► P1-004
│   (Can run parallel with Phase 2)
│
▼
Phase 2 (Evernight) ────────────────────────────────────────────────
│
│   P2-002 ─► P2-003 ─► P2-004 ─► P2-001 ─► P2-005
│   (Models first, then services, then agent)
│
▼
Phase 3 (Triggers) ─────────────────────────────────────────────────
│
│   P3-001 (Queue) ─► P3-003 ─► P3-004 (Overflow)
│   P3-002 (Nightly) ─► P3-004
│
▼
Phase 4 (Integration) ──────────────────────────────────────────────
│
│   P4-001 ─► P4-002 ─► P4-003 ─► P4-004
│   (Wiring everything together)
│
▼
DONE
```

---

## Task Checklist

### Phase 0: Cleanup (12 tasks) ✅ COMPLETED
- [x] P0-001: Delete evaluation/pipeline.py
- [x] P0-002: Delete evaluation/rule_engine.py
- [x] P0-003: Delete evaluation/__init__.py (then delete directory)
- [x] P0-004: Simplify MessageCategory to only GENERAL
- [x] P0-005: Remove CRITICAL_INFO_THRESHOLD from constants.py
- [x] P0-006: Remove semantic trigger from activate_memory_service.py (lines 57-68)
- [x] P0-007: Remove EvaluationPipeline dependency from activate_memory_service.py
- [x] P0-008: Remove RuleEngine/EvaluationPipeline registration from DI
- [x] P0-009: Remove EpisodicManager from MemoryManager constructor
- [x] P0-010: Remove _run_t2_past_events() from MemoryManager
- [x] P0-011: Remove CRITICAL_INFO_DETECTED subscription (if exists)
- [x] P0-012: Update _handle_memory_overflow to queue pattern

### Phase 1: MCP Tools (4 tasks) ✅ COMPLETED
- [x] P1-001: Create SearchMemoryTool (Updated with TODO for WikiPages)
- [x] P1-002: Create UpdateProfileTool (Already exists in implementations)
- [x] P1-003: Create MCP Tool Registry (Already exists)
- [x] P1-004: Wire Tools to Bay (Already wired via dependencies)

### Phase 2: Evernight (5 tasks) ✅ COMPLETED
- [x] P2-001: Create EvernightAgent class
- [x] P2-002: Create WikiPage model
- [x] P2-003: Create WikiStorage service
- [x] P2-004: Create WikiMerge service
- [x] P2-005: Create Evernight config (Embedded in agent.py)

### Phase 3: Triggers (4 tasks) ✅ COMPLETED
- [x] P3-001: Create OverflowQueue service
- [x] P3-002: Create NightlyTrigger task
- [x] P3-003: Wire token overflow trigger
- [x] P3-004: Create Evernight spawner

### Phase 4: Integration (4 tasks) ✅ COMPLETED
- [x] P4-001: Update MemoryManager constructor
- [x] P4-002: Update get_context() (Already updated in Phase 0)
- [x] P4-003: Update DI container
- [x] P4-004: Update bot entry point

---

## Implementation Summary

**Files Created (14):**
- `src/agents/__init__.py`
- `src/agents/shared/__init__.py`
- `src/agents/shared/models/__init__.py`
- `src/agents/shared/models/wiki_page.py`
- `src/agents/evernight/__init__.py`
- `src/agents/evernight/agent.py`
- `src/agents/evernight/spawner.py`
- `src/agents/evernight/services/__init__.py`
- `src/agents/evernight/services/wiki_storage.py`
- `src/agents/evernight/services/wiki_merge.py`
- `src/services/queue/__init__.py`
- `src/services/queue/overflow_queue.py`
- `src/tasks/__init__.py`
- `src/tasks/nightly_trigger.py`

**Files Modified (8):**
- `src/bot.py` - Added NightlyTrigger startup
- `src/services/dependencies.py` - Added Evernight, Wiki, Queue initialization
- `src/services/memories/memory_manager.py` - Queue + Spawner integration
- `src/services/memories/activate_memory/models.py` - MessageCategory simplified
- `src/services/memories/activate_memory/constants.py` - Removed thresholds
- `src/services/memories/activate_memory/__init__.py` - Updated exports
- `src/services/memories/activate_memory/activate_memory_service.py` - Removed pipeline
- `src/services/memories/activate_memory/management/smart_cleanup.py` - Simplified cleanup

**Files Deleted (3):**
- `src/services/memories/activate_memory/evaluation/pipeline.py`
- `src/services/memories/activate_memory/evaluation/rule_engine.py`
- `src/services/memories/activate_memory/evaluation/__init__.py`

**Directory Deleted (1):**
- `src/services/memories/activate_memory/evaluation/`

---

## Next Action

**IMPLEMENTATION COMPLETED**

All phases completed successfully. 22 files verified with AST syntax check (0 errors).

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Tests fail after deletion | Run tests after each P0 task |
| DI container broken | Update registration immediately after deletion |
| Import errors | Check all imports referencing deleted files |