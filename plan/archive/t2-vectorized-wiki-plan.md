---
goal: Implement T2 (Evernight Agent) memory consolidation using Vectorized Wiki Architecture with Upsert pattern and LLM-based merge
version: "1.0"
date_created: "2026-04-23"
last_updated: "2026-04-23"
status: Planned
tags:
  - feature
  - memory-system
  - evernight
  - vectorized-wiki
  - upsert-pattern
  - llm-merge
---

# T2 Vectorized Wiki Architecture Implementation Plan

## Introduction

Implementation of T2 (Evernight Agent) using **Vectorized Wiki Architecture** - a paradigm shift from TopicChunkRecord/RAG to consolidated Wiki Pages.

**CRITICAL: This replaces the previous TopicChunkRecord/RAG approach**

**Architecture Decision Rationale:**
- RAG Chunking: Excellent for static Document QA, but fatal weakness for human memory: "People change, Documents don't"
- Vectorized Wiki: Prioritizes information consistency (State) over change history (Log)
- For companion bot, Evernight acts as Memory Manager, not just Tape Recorder

**Parent Plans:**
- `TWIN_SOULS_ARCHITECTURE.md` - Twin Souls Architecture
- `T2_TTL_AND_TRIGGER.md` - TTL & Trigger Decisions

---

## Architecture Decisions (CONFIRMED)

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | Wiki Pages as Qdrant records with Upsert | Same topic = Same ID = Overwrite/Merge |
| 2 | Single storage: Qdrant only | No Redis needed for metadata mapping |
| 3 | page_id = hash(user_id + canonical_topic) | Deterministic ID for Upsert |
| 4 | LLM Merge at ingestion time | Conflicts resolved before storage |
| 5 | Simplified LINT: TTL cleanup only | No contradiction scan (handled at Merge) |

---

## WikiPagePayload Model

```python
# src/agents/shared/models/wiki_page.py

class WikiPagePayload(BaseModel):
    """Consolidated Wiki Page stored in Qdrant."""
    
    # === Identity ===
    page_id: str              # hash(user_id + canonical_topic)
    user_id: str
    canonical_topic: str      # "Evangelion_Anime" (LLM normalized)
    
    # === Content ===
    category: str             # entertainment, relationship, work_study, casual, daily_mood
    current_summary: str      # Consolidated summary (NEWEST state)
    key_points: List[str]     # Accumulated facts (resolved)
    importance: int           # 1-5 scale
    
    # === TTL ===
    ttl_days: int             # 7-90 days by importance
    created_at: datetime
    last_updated: datetime    # Last merge
    last_accessed: datetime   # Last retrieval
    access_count: int
    
    # === Optional ===
    history_log: List[str]    # ["rating: 9→8", "watched ep 7"]
    confidence: float         # 0-1
    embedding: List[float]    # Vector of current_summary
```

---

## page_id Hash Logic

```python
def generate_page_id(user_id: str, canonical_topic: str) -> str:
    """
    Deterministic page ID for Upsert.
    
    Same user + same topic = Same ID
    Example:
        generate_page_id("user123", "Evangelion_Anime")
        → "a3b7c9d2"
    """
    combined = f"{user_id}:{canonical_topic.lower()}"
    hash_bytes = hashlib.sha256(combined.encode('utf-8')).digest()
    return hash_bytes[:8].hex()
```

---

## INGEST Flow (Read-Merge-Write)

```
T1 overflow → Evernight receives snapshot
├── EXTRACT: LLM splits into topics with canonical names
├── FOR EACH TOPIC:
│   ├── page_id = hash(user_id + canonical_topic)
│   ├── LOOKUP: Query Qdrant by page_id
│   ├── DECISION:
│   │   ├── NEW: Create WikiPage → Embed → Upsert
│   │   └── EXISTS: Retrieve old → LLM Merge → Embed → Upsert
│   └────────────────────────────────────────────────────────────
│   LLM Merge Logic:
│   ├── Input: old_page + new_info
│   ├── Detect contradictions
│   ├── Resolve (latest wins for mutable, append for accumulative)
│   ├── Update current_summary, key_points
│   ├── Append to history_log if major change
│   └── Return: merged WikiPagePayload
```

---

## LLM Merge Prompt Template

```python
WIKI_MERGE_PROMPT = """
Role: Memory_Consolidator
Task: Merge_Wiki_Pages

Input:
  old_page: {old_page_json}
  new_info: {new_info_json}

Merge_Rules:
  1. MUTABLE_FACTS_REPLACE: Preferences, ratings, opinions
     - old: "rating 9/10" + new: "rating 8/10" → use 8/10
     - Add to history_log: "rating: 9→8"
     
  2. ACCUMULATIVE_FACTS_APPEND: Events, experiences
     - old: "watched ep 1-6" + new: "watched ep 7-13"
     → combine: "watched ep 1-13"
     
  3. CONTRADICTIONS_RESOLVE: Prefer NEWEST (user's current state)

Output: JSON with merged current_summary, key_points, history_log
"""
```

---

## QUERY Flow (Bay Retrieval)

```
Bay needs T2 → Vector search Qdrant
├── Embed query → Vector search
├── Filter by user_id, relevance >= 0.5
├── Return WikiPages (consolidated, no contradictions)
├── Format for LLM: "[topic] key_points - summary"
├── Refresh: last_accessed = NOW, access_count += 1
```

---

## LINT Flow (11PM Daily)

```
Scheduled Trigger
├── For each user:
│   ├── For each WikiPage:
│   │   ├── calculate_relevance(now)
│   │   ├── If relevance < 0.1 → DELETE
│   │   └────────────────────────────────────────────────────────
│   ONLY TTL cleanup (NO contradiction scan)
```

---

## TTL Relevance Formula

```python
relevance = decay_factor * access_boost

where:
  decay_factor = exp(-days_since_access / effective_ttl)
  access_boost = min(1.5, 1 + 0.1 * access_count)
  effective_ttl = ttl_days * access_boost

Thresholds:
  ≥ 0.5 → Include in search
  < 0.1 → Delete
```

**TTL by Importance:**
| Importance | TTL | Examples |
|------------|-----|----------|
| 5 | 90 days | Relationship milestones, identity |
| 4 | 60 days | Crush, family, friends |
| 3 | 30 days | Entertainment, hobbies |
| 2 | 14 days | Casual observations |
| 1 | 7 days | Random chat, greetings |

---

## Implementation Phases

### Phase 1: Data Models (2 days)

| Task | Description | File | Status |
|------|-------------|------|--------|
| P1-001 | Create agents directory | `src/agents/__init__.py` | ☐ |
| P1-002 | Create shared models | `src/agents/shared/models/__init__.py` | ☐ |
| P1-003 | Create TopicCategory enum | `src/agents/shared/models/topic_category.py` | ☐ |
| P1-004 | Create WikiPagePayload model | `src/agents/shared/models/wiki_page.py` | ☐ |
| P1-005 | Implement generate_page_id() | `wiki_page.py` | ☐ |
| P1-006 | Implement calculate_relevance() | `wiki_page.py` | ☐ |
| P1-007 | Implement serialization | `wiki_page.py` | ☐ |
| P1-008 | Write unit tests | `tests/agents/shared/models/` | ☐ |

---

### Phase 2: Wiki Storage (3 days)

| Task | Description | File | Status |
|------|-------------|------|--------|
| P2-001 | Create Evernight directory | `src/agents/evernight/__init__.py` | ☐ |
| P2-002 | Create WikiStorage class | `src/agents/evernight/services/wiki/storage.py` | ☐ |
| P2-003 | Implement lookup_by_page_id() | Storage | ☐ |
| P2-004 | Implement upsert_page() | Storage | ☐ |
| P2-005 | Implement semantic_search() | Storage | ☐ |
| P2-006 | Write unit tests | `tests/agents/evernight/services/wiki/` | ☐ |

---

### Phase 3: Merge Logic (3 days)

| Task | Description | File | Status |
|------|-------------|------|--------|
| P3-001 | Define merge prompts | `src/agents/evernight/services/wiki/prompts.py` | ☐ |
| P3-002 | Create WikiMergeService | `merge_service.py` | ☐ |
| P3-003 | Implement merge_pages() | MergeService | ☐ |
| P3-004 | Write unit tests | `test_merge.py` | ☐ |

---

### Phase 4: Consolidation Flow (4 days)

| Task | Description | File | Status |
|------|-------------|------|--------|
| P4-001 | Create WikiExtractor | `extractor.py` | ☐ |
| P4-002 | Implement extract_topics() | Extractor | ☐ |
| P4-003 | Create WikiConsolidationService | `consolidation_service.py` | ☐ |
| P4-004 | Implement full INGEST flow | ConsolidationService | ☐ |
| P4-005 | Write integration tests | `test_consolidation.py` | ☐ |

---

### Phase 5: Retrieval & Integration (3 days)

| Task | Description | File | Status |
|------|-------------|------|--------|
| P5-001 | Create WikiRetrievalService | `retrieval.py` | ☐ |
| P5-002 | Implement search_wiki() | RetrievalService | ☐ |
| P5-003 | Create A2A messages | `src/agents/shared/a2a/messages.py` | ☐ |
| P5-004 | Create Evernight agent | `src/agents/evernight/agent.py` | ☐ |
| P5-005 | Update MemoryManager | `memory_manager.py` (T1 overflow → A2A) | ☐ |
| P5-006 | Write integration tests | `test_retrieval.py` | ☐ |

---

### Phase 6: LINT (2 days)

| Task | Description | File | Status |
|------|-------------|------|--------|
| P6-001 | Create WikiLintService | `lint_service.py` | ☐ |
| P6-002 | Implement cleanup_expired() | LintService | ☐ |
| P6-003 | Create ScheduledTrigger | `scheduled_trigger.py` (11PM) | ☐ |
| P6-004 | Write unit tests | `test_lint.py` | ☐ |

---

## Files Summary

**New Files:** 20
**Modified Files:** 2 (`memory_manager.py`, `settings.py`)
**Test Files:** 8
**Total Tasks:** 35

---

## Risks

| Risk | Mitigation |
|------|------------|
| LLM merge invalid JSON | Pydantic validation + retry |
| Canonical naming inconsistent | Strict prompt rules + examples |
| Merge latency | Async processing |

---

## Next Action

**Start Phase 1: Data Models**
- Create WikiPagePayload model
- Implement page_id hash
- Write unit tests