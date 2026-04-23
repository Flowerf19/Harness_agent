# T2 TTL & Trigger Mechanism - Detailed Plan

## Overview
Breakdown of TTL mechanism và T2 trigger logic cho Evernight.

**Parent Plan:** `TWIN_SOULS_ARCHITECTURE.md`

---

## Part 1: TTL Mechanism (Time-To-Live)

### 1.1 Concept

```
Memory Decay = Natural Forgetting

┌──────────────────────────────────────────────────────────────┐
│                    TTL LIFECYCLE                              │
│                                                              │
│  Create ──► Decay ──► Access ──► Refresh ──► Decay ──► ...   │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ Entry created: TTL = 30 days                            │ │
│  │ Day 7: relevance = 0.79 (decay)                        │ │
│  │ Day 7: USER ASKS about anime → ACCESS!                  │ │
│  │         → last_accessed = NOW                           │ │
│  │         → access_count += 1                             │ │
│  │         → relevance = 1.0 (refreshed)                   │ │
│  │ Day 14: relevance = 0.86 (decay from day 7)            │ │
│  │ Day 21: USER ASKS again → ACCESS!                       │ │
│  │         → relevance = 1.0 (refreshed again)             │ │
│  │         → access_count = 2                              │ │
│  │         → effective TTL boost = 30 * 1.2 = 36 days     │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                              │
│  Entry không được access → decay tiếp                        │
│  relevance < threshold (e.g., 0.3) → considered "forgotten"  │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 1.2 TTL Fields

```python
# TopicChunkRecord fields for TTL
{
    "ttl_days": 30,           # Base TTL (assigned at creation)
    "created_at": "2026-04-21T00:30:00Z",
    "last_accessed": "2026-04-21T00:30:00Z",
    "access_count": 0,        # Number of times retrieved
}
```

### 1.3 TTL Assignment (At Creation)

| Importance | Base TTL | Examples |
|------------|----------|----------|
| 5 (critical) | 90 days | Relationship milestones, personal identity |
| 4 (high) | 60 days | Crush, family, close friends |
| 3 (medium) | 30 days | Entertainment, hobbies, preferences |
| 2 (low) | 14 days | Casual observations |
| 1 (minimal) | 7 days | Random chat, greetings |

**Importance Assignment Method:**
```python
# In Evernight prompt
IMPORTANCE_RULES = {
    "relationship": 4,      # Default for relationship category
    "work_study": 3,        # Default for work/study
    "entertainment": 3,     # Default for entertainment
    "daily_mood": 2,        # Mood is fleeting
    "casual": 1,            # Casual chat
}

# Override rules:
# - User mentions crush → importance 4+
# - User reveals personal info (name, age, job) → importance 5
# - Deep discussion (≥5 exchanges on topic) → +1 boost
```

### 1.4 Decay Formula

```python
def calculate_relevance(entry: TopicChunkRecord, current_time: datetime) -> float:
    """
    Calculate current relevance score (0-1).

    Formula:
    relevance = decay_factor * access_boost

    Where:
    - decay_factor = exp(-days_since_access / effective_ttl)
    - access_boost = min(1.5, 1 + 0.1 * access_count)
    - effective_ttl = ttl_days * access_boost
    """
    days_since_access = (current_time - entry.last_accessed).days

    # Access boost (max 1.5x)
    access_boost = min(1.5, 1 + 0.1 * entry.access_count)

    # Effective TTL (longer if accessed more)
    effective_ttl = entry.ttl_days * access_boost

    # Decay factor (exponential decay)
    decay_factor = math.exp(-days_since_access / effective_ttl)

    return decay_factor

# Example:
# Entry: ttl_days=30, access_count=2, last_accessed=7 days ago
# access_boost = 1 + 0.1*2 = 1.2
# effective_ttl = 30 * 1.2 = 36 days
# decay_factor = exp(-7/36) = 0.83
# relevance = 0.83
```

### 1.5 Retrieval Flow with TTL Refresh

```
┌──────────────────────────────────────────────────────────────┐
│                RETRIEVAL WITH TTL REFRESH                    │
│                                                              │
│  1. SEARCH: Query Qdrant for matching topics                 │
│     ├── Vector similarity search                             │
│     └── Filter by user_id                                    │
│                                                              │
│  2. CALCULATE: Apply TTL decay to results                    │
│     ├── For each result: calculate_relevance()               │
│     ├── Sort by: similarity * relevance                      │
│     └── Filter: relevance >= MIN_THRESHOLD (0.3)             │
│                                                              │
│  3. RETURN: Top N results to context                         │
│                                                              │
│  4. REFRESH: Update accessed entries                         │
│     ├── For each returned entry:                             │
│     │   ├── last_accessed = NOW                              │
│     │   ├── access_count += 1                                │
│     │   └── Save to Qdrant                                   │
│                                                              │
│  Result: Accessed memories live longer!                      │
└──────────────────────────────────────────────────────────────┘
```

### 1.6 TTL Thresholds

| Threshold | Action |
|-----------|---------|
| relevance >= 0.7 | High relevance - include in search results |
| relevance >= 0.3 | Medium - still searchable |
| relevance < 0.3 | Low - considered "forgotten" - skip from results |
| relevance < 0.1 | Very low - candidate for cleanup/delete |

### 1.7 Cleanup Process (Optional)

```python
# Evernight runs cleanup periodically (e.g., weekly)
async def cleanup_forgotten_memories():
    """Delete entries with very low relevance."""

    for user_id in get_all_users():
        entries = await qdrant.get_all_user_entries(user_id)

        for entry in entries:
            relevance = calculate_relevance(entry, now)

            if relevance < 0.1:
                # Mark for deletion or delete immediately
                await qdrant.delete(entry.entry_id)
                logger.info(f"Deleted forgotten entry: {entry.topic}")
```

---

## Part 2: T2 Trigger Mechanism

### 2.1 Dual Trigger Concept

```
┌──────────────────────────────────────────────────────────────┐
│                    T2 TRIGGER SOURCES                         │
│                                                              │
│  ┌─────────────────┐     ┌─────────────────┐                 │
│  │ SCHEDULED       │     │ T1 OVERFLOW     │                 │
│  │ (Primary)       │     │ (Fallback)      │                 │
│  │                 │     │                 │                 │
│  │ • 11PM-6AM      │     │ • Token limit   │                 │
│  │ • Daily run     │     │ • A2A trigger   │                 │
│  │ • Batch all     │     │ • Single user   │                 │
│  │   users         │     │   only          │                 │
│  └─────────────────┘     └─────────────────┘                 │
│         │                       │                            │
│         ▼                       ▼                            │
│  ┌─────────────────────────────────────────────┐             │
│  │              EVERNIGHT PROCESS               │             │
│  │                                             │             │
│  │  Scheduled: Batch consolidation (all users) │             │
│  │  Overflow:  Single user consolidation       │             │
│  │                                             │             │
│  └─────────────────────────────────────────────┘             │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 Trigger 1: Scheduled (Primary)

**Timing:** 11PM - 6AM (configurable)

**Implementation:**
```python
# evernight/triggers.py

from apscheduler.schedulers.asyncio import AsyncIOScheduler

class ScheduledTrigger:
    """Scheduled trigger for daily consolidation."""

    def __init__(self, evernight_agent):
        self.agent = evernight_agent
        self.scheduler = AsyncIOScheduler()

    def start(self):
        """Start scheduled trigger."""
        # Run at 11PM daily
        self.scheduler.add_job(
            self.agent.run_batch_consolidation,
            trigger='cron',
            hour=23,  # 11PM
            minute=0,
            id='daily_consolidation',
        )
        self.scheduler.start()

    def stop(self):
        """Stop scheduler."""
        self.scheduler.shutdown()
```

**Batch Consolidation Flow:**
```
┌──────────────────────────────────────────────────────────────┐
│              SCHEDULED BATCH CONSOLIDATION                    │
│                                                              │
│  1. GET: All users with T1 data from today                   │
│     ├── Query Redis for active T1 buffers                    │
│     ├── Filter: last_activity within 24h                     │
│     └── List of user_ids to process                          │
│                                                              │
│  2. FOR EACH USER:                                           │
│     ├── Read T1 buffer (Redis)                               │
│     ├── Generate topic-level summary                         │
│     ├── Create TopicChunkRecords                             │
│     ├── Store to Qdrant                                      │
│     ├── Clear T1 buffer (mark as consolidated)               │
│     └── Send A2A notification to Bay                         │
│                                                              │
│  3. LOG: Consolidation summary                               │
│     ├── Total users processed                                │
│     ├── Total topics created                                 │
│     ├── Errors encountered                                   │
│                                                              │
│  4. CLEANUP: TTL decay check (optional)                      │
│     ├── Scan for low relevance entries                       │
│     └── Delete if relevance < 0.1                            │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 2.3 Trigger 2: T1 Overflow (Fallback)

**Condition:** T1 buffer reaches token threshold

**Current T1 Implementation (Verified):**

```python
# From constants.py
MAX_WORKING_TOKENS = 2000   # Overflow threshold
TARGET_SAFE_TOKENS = 1000   # Cleanup target

# From activate_memory_service.py
# Flow: add_message() → check tokens → emit event
if current_tokens >= MAX_WORKING_TOKENS:
    snapshot = await self.storage.get_entries(user_id)
    self.events.emit(
        ActiveMemoryEvent.TOKEN_LIMIT_REACHED,
        user_id,
        data={"snapshot": snapshot, "current_tokens": current_tokens},
    )

# From memory_manager.py
# Handler: T2 ingest → T1 cleanup
async def _handle_memory_overflow(self, event_type: str, user_id: str, data: dict):
    snapshot = data.get("snapshot", [])
    success = await self.t2.ingest_snapshot(user_id, snapshot)  # Current T2
    if success:
        await self.t1.force_cleanup(user_id)  # Reduce to TARGET_SAFE_TOKENS
```

**Key Findings:**
- **Threshold:** `MAX_WORKING_TOKENS = 2000`
- **Event payload:** `snapshot` = list of all T1 entries (full data transfer)
- **Cleanup:** After T2 success, T1 reduced to `1000 tokens`
- **Current T2:** `EpisodicManager.ingest_snapshot()` → creates EpisodicRecords

**New Behavior with Evernight:**
```
┌──────────────────────────────────────────────────────────────┐
│                T1 OVERFLOW FLOW                               │
│                                                              │
│  BAY (Main Bot)                                              │
│  ├── User chats → T1 buffer fills                            │
│  ├── Token count reaches THRESHOLD                           │
│  │   └── Threshold: configurable (e.g., 8000 tokens)         │
│  ├── Bay sends A2A message:                                  │
│  │   {                                                       │
│  │     "type": "t1_overflow",                                │
│  │     "payload": {                                          │
│  │       "user_id": "xxx",                                   │
│  │       "t1_data": "...",  # OR just signal                 │
│  │       "urgency": "normal"                                 │
│  │     }                                                     │
│  │   }                                                       │
│  └── Bay continues serving user (no blocking)                │
│                                                              │
│  EVERNIGHT (Twin Agent)                                       │
│  ├── Receives A2A message                                    │
│  ├── Queues consolidation task                               │
│  ├── Processes single user                                   │
│  ├── Creates TopicChunks                                     │
│  ├── Stores to Qdrant                                        │
│  ├── Sends A2A notification back:                            │
│  │   {                                                       │
│  │     "type": "t2_consolidated",                            │
│  │     "payload": {                                          │
│  │       "user_id": "xxx",                                   │
│  │       "topics_count": 3,                                  │
│  │       "status": "success"                                 │
│  │     }                                                     │
│  │   }                                                       │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 2.4 A2A Messages for T2 Trigger

```python
# shared/a2a/messages.py

# T1 Overflow message (Bay → Evernight)
class T1OverflowPayload(BaseModel):
    user_id: str
    token_count: int
    urgency: Literal["normal", "high"] = "normal"
    # Option A: Include T1 data
    t1_data: str | None = None
    # Option B: Signal only (Evernight reads from Redis)
    signal_only: bool = True

# T2 Consolidated message (Evernight → Bay)
class T2ConsolidatedPayload(BaseModel):
    user_id: str
    topics_count: int
    topics: List[str]  # Topic names created
    status: Literal["success", "partial", "failed"]
    error_message: str | None = None
```

### 2.5 Trigger Priority & Conflict

```
┌──────────────────────────────────────────────────────────────┐
│                    TRIGGER CONFLICT HANDLING                  │
│                                                              │
│  Scenario: User active at 11PM                               │
│  ├── Scheduled trigger fires                                 │
│  ├── User's T1 buffer still being filled                     │
│  ├── Evernight checks: is user still active?                 │
│  │   ├── If active: Skip this user (wait for next cycle)     │
│  │   ├── If inactive: Consolidate normally                   │
│  │                                                           │
│  Scenario: Overflow trigger + Scheduled overlap              │
│  ├── User triggered overflow at 10:58PM                      │
│  ├── Scheduled runs at 11PM                                  │
│  ├── Evernight tracks: recently_consolidated[user_id]        │
│  ├── Scheduled skips users consolidated in last 1h           │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 2.6 Configuration

```python
# evernight/config.py

class TriggerConfig:
    # Scheduled trigger
    SCHEDULED_HOUR: int = 23  # 11PM
    SCHEDULED_MINUTE: int = 0

    # T1 overflow threshold (in Bay)
    T1_OVERFLOW_THRESHOLD: int = 8000  # tokens

    # Conflict avoidance
    CONSOLIDATION_COOLDOWN: int = 3600  # 1 hour in seconds

    # Batch settings
    BATCH_SIZE: int = 10  # Process 10 users at a time
    BATCH_DELAY: float = 1.0  # 1 second between batches
```

---

## Part 3: Implementation Tasks

### TTL Implementation

- [ ] Create `TopicChunkRecord` model with TTL fields
- [ ] Implement `calculate_relevance()` function
- [ ] Implement TTL assignment logic (importance → TTL mapping)
- [ ] Update retrieval to calculate + filter by relevance
- [ ] Implement refresh on retrieval (update last_accessed, access_count)
- [ ] Add cleanup task for forgotten entries (optional, Phase 5)

### Trigger Implementation

- [ ] Implement `ScheduledTrigger` class
- [ ] Configure APScheduler in Evernight
- [ ] Implement batch consolidation flow
- [ ] Define T1 overflow threshold in Bay
- [ ] Implement A2A `t1_overflow` message handler in Evernight
- [ ] Implement single-user consolidation for overflow
- [ ] Add consolidation cooldown tracking (avoid duplicate)
- [ ] Implement A2A `t2_consolidated` notification

---

## Decisions (CONFIRMED - 23/04/2026)

| # | Question | Decision | Reason |
|---|----------|----------|--------|
| 1 | Importance assignment | **C: Hybrid** | Category default + LLM boost based on depth |
| 2 | Relevance threshold | **B: 0.5** | Stricter, tune later if needed |
| 3 | Cleanup timing | **C: Lazy** | Check on retrieval, simpler implementation |
| 4 | T1 overflow data transfer | **A: Send snapshot** | Keep current behavior, simpler migration |
| 5 | Replace `_handle_memory_overflow` | **A: Replace handler** | Cleaner, single flow |
| 6 | Consolidation cooldown | **B: Check T1 timestamp** | Use existing T1 data |
| 7 | Active user detection | **A: T1 timestamp** | Use T1's existing timestamp |
| 8 | MAX_WORKING_TOKENS | **A: Keep 2000** | Current works well |
| 9 | Transition old T2 | **A: Adapter pattern** | Gradual migration, backward compatible |

---

## Implementation Phases

### Phase 1: Data Models (Foundation)
**Goal:** Create new TopicChunkRecord model with TTL fields

- Create `TopicChunkRecord` model in `src/agents/shared/models/`
- TTL fields: `ttl_days`, `created_at`, `last_accessed`, `access_count`
- Content fields: `topic`, `category`, `importance`, `key_points`, `summary`
- Category enum: `entertainment`, `relationship`, `work_study`, `casual`, `daily_mood`

### Phase 2: TTL Mechanism
**Goal:** Implement TTL calculation and refresh logic

- `calculate_relevance()` function in `src/agents/evernight/services/t2_memory/`
- TTL assignment: category → base TTL + LLM boost
- Retrieval flow: calculate relevance → filter ≥ 0.5 → refresh accessed entries
- Lazy cleanup: delete entries with relevance < 0.1 during retrieval

### Phase 3: Consolidation Logic
**Goal:** Topic-level consolidation from T1 data

- `TopicExtractor` class: LLM extracts topics from T1 snapshot
- Split single snapshot into multiple TopicChunkRecords
- Importance assignment: category default + depth boost
- Embedding strategy: embed `topic + key_points` only

### Phase 4: Trigger Implementation
**Goal:** Dual trigger (scheduled + overflow)

- `ScheduledTrigger` class with APScheduler (11PM daily)
- Batch consolidation: process all users with T1 activity
- T1 overflow: keep current flow, emit A2A message to Evernight
- Cooldown tracking: check T1 last_activity timestamp

### Phase 5: Transition & Adapter
**Goal:** Gradual migration from old T2

- `T2RetrievalAdapter`: query both old EpisodicRecords + new TopicChunks
- Old records: keep as-is, no new writes
- New writes: only TopicChunkRecords
- Eventually migrate old data (optional)

---

## Next Steps

1. ✅ **Decisions confirmed** - All 9 questions answered
2. → **Create detailed implementation plan** - Machine-readable tasks
3. → **Phase 1 implementation** - Start with data models