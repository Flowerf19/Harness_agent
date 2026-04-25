# Plan: Twin Souls Architecture - Bay & Evernight

## Overview
**Concept:** Two independent agents working together via A2A (Agent-to-Agent) communication.
- **Bay** = Main Discord bot (current)
- **Evernight** = Twin agent for T2 memory + future functions

**Status:** ✅ CHỐT KIẾN TRÚC (22/04/2026) - Phase 1: T2 Memory consolidation

---

## Twin Souls Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    TWIN SOULS ARCHITECTURE                           │
│                                                                     │
│   ┌─────────────────────┐      A2A       ┌─────────────────────┐    │
│   │        BAY          │◄──────────────►│     EVERNIGHT       │    │
│   │   (Main Discord)    │   Redis Pub/Sub│   (Twin Agent)      │    │
│   │                     │                │                     │    │
│   │ • Discord gateway   │                │ • T2 Memory ✓       │    │
│   │ • T1 Active Memory  │                │ • Error recovery    │    │
│   │ • T3 Core Memory    │                │ • Maintenance       │    │
│   │ • Primary LLM       │                │ • Analytics         │    │
│   │ • User chat         │                │ • Own LLM config    │    │
│   └─────────────────────┘                └─────────────────────┘    │
│                                                                     │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │                    SHARED INFRASTRUCTURE                     │   │
│   │  • Qdrant (T2 storage)                                       │   │
│   │  • Embedding Service                                         │   │
│   │  • Tools (MCP)                                               │   │
│   │  • Models (EpisodicRecord, etc.)                             │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Decisions Made (FINAL)

### Architecture Decisions

| Item | Decision | Notes |
|------|----------|-------|
| **Agent Structure** | `src/agents/bay/` + `src/agents/evernight/` | Twin folders, refactor current src/ |
| **Shared Layer** | `src/agents/shared/` | Qdrant, Embedding, Tools, Models |
| **A2A Method** | **Redis Pub/Sub** | Message passing between agents |
| **A2A Messages** | Incremental | Define per feature (T2 first) |
| **Agent Independence** | Evernight has own LLM config | Fallback when Bay errors |

### T2 Memory Decisions

| Item | Decision | Notes |
|------|----------|-------|
| **Agent Name** | **Evernight** | Custom name chosen by user |
| **Runtime** | **Dual Trigger**: 11PM-6AM + Token threshold | Scheduled window + fallback trigger |
| **Model Config** | **Separate** | Fallback independent, không phụ thuộc bot chính |
| **T3 Handling** | **Tách biệt** | Evernight chỉ lo T2, T3 update do main bot |
| **T2 Strategy** | **Replace** current T2 structure | Evernight thay thế cơ chế T1 overflow hiện tại |
| **Document Structure** | Option B (Topic-Level Chunks) | One entry per topic per day |
| **TTL Mechanism** | Smart TTL + Refresh on retrieval | Decay + access_boost |
| **Category Taxonomy** | Fixed (5 categories) | entertainment, relationship, work_study, casual, daily_mood |
| **Embedding Strategy** | Approach 2 (Focused) | Embed topic + key_points only |

---

## Directory Structure

```
src/agents/
├── bay/                      # Main agent (Bảy)
│   ├── agent.py              # CoreBot wrapper (from bot.py)
│   ├── config.py             # Own LLM config
│   ├── discord/              # Cogs (moved from src/cogs)
│   │   ├── chat_gateway.py
│   │   ├── admin_channels.py
│   │   └── user_commands.py
│   ├── services/
│   │   ├── t1_memory/        # Active Memory (moved)
│   │   ├── t3_memory/        # Core Memory (moved)
│   │   ├── chat_coordinator/ # (moved)
│   │   └── llm/              # Primary LLM service
│   └── entrypoint.py         # Discord bot entry
│
├── evernight/                # Twin agent
│   ├── agent.py              # Evernight core class
│   ├── config.py             # Own LLM config (fallback)
│   ├── services/
│   │   ├── t2_memory/        # Phase 1: T2 consolidation
│   │   │   ├── consolidation/
│   │   │   ├── storage/
│   │   │   └── retrieval/
│   │   └── recovery/         # Future: error recovery
│   ├── triggers.py           # Dual trigger (scheduled + token)
│   ├── a2a/                  # A2A communication
│   │   ├── publisher.py      # Send messages to Bay
│   │   └ subscriber.py       # Listen from Bay
│   └── entrypoint.py         # Evernight process entry
│
├── shared/                   # Shared infrastructure
│   ├── embedding/            # Embedding service (both use)
│   ├── qdrant/               # Qdrant connection (both use)
│   ├── tools/                # MCP Tools (both use)
│   ├── models/               # EpisodicRecord, etc.
│   ├── a2a/                  # A2A protocol definitions
│   │   ├── channels.py       # Redis channel names
│   │   └ messages.py         # Message schemas
│   │   └ protocol.py         # A2A base class
│   └── config.py             # Shared config (env vars)
│
└── __init__.py
```

---

## A2A Protocol (Draft)

### Redis Channels

```python
# src/agents/shared/a2a/channels.py

A2A_CHANNELS = {
    "bay_to_evernight": "a2a:bay:evernight",     # Bay → Evernight
    "evernight_to_bay": "a2a:evernight:bay",     # Evernight → Bay
    "broadcast": "a2a:broadcast",                 # Both listen
}
```

### Message Schema

```python
# src/agents/shared/a2a/messages.py

from pydantic import BaseModel
from typing import Literal
from datetime import datetime

class A2AMessage(BaseModel):
    id: str
    sender: Literal["bay", "evernight"]
    receiver: Literal["bay", "evernight", "broadcast"]
    type: str  # Message type (defined per feature)
    payload: dict
    timestamp: datetime
    reply_to: str | None = None  # For request-response pattern
    correlation_id: str | None = None  # For request-response matching

# All A2A message types
A2A_MESSAGE_TYPES = {
    # T2 Memory (Phase 1)
    "t1_overflow": {"from": "bay", "to": "evernight", "pattern": "fire"},
    "t2_consolidated": {"from": "evernight", "to": "bay", "pattern": "fire"},
    "t2_search_request": {"from": "bay", "to": "evernight", "pattern": "request"},
    "t2_search_result": {"from": "evernight", "to": "bay", "pattern": "response"},
    "t2_consolidation_failed": {"from": "evernight", "to": "bay", "pattern": "fire"},

    # Health & Monitoring
    "health_check": {"from": "bay", "to": "evernight", "pattern": "request"},
    "health_response": {"from": "evernight", "to": "bay", "pattern": "response"},
    "error_notification": {"from": "evernight", "to": "bay", "pattern": "fire"},

    # Admin Control
    "manual_trigger": {"from": "bay", "to": "evernight", "pattern": "fire"},
    "shutdown_request": {"from": "bay", "to": "evernight", "pattern": "fire"},

    # Future: Error Recovery
    "recovery_request": {"from": "bay", "to": "evernight", "pattern": "request"},
    "recovery_result": {"from": "evernight", "to": "bay", "pattern": "response"},
}
```

### A2A Base Class

```python
# src/agents/shared/a2a/protocol.py

import asyncio
import json
import uuid
from redis.asyncio import Redis
from .channels import A2A_CHANNELS
from .messages import A2AMessage

class A2AProtocol:
    """Base A2A communication class with request-response support."""

    def __init__(self, redis: Redis, agent_name: str):
        self.redis = redis
        self.agent_name = agent_name
        self.handlers = {}  # message_type → handler function
        self.pending_requests = {}  # correlation_id → asyncio.Future
        self._subscriber_task = None

    async def publish(self, receiver: str, msg_type: str, payload: dict, timeout: float = 5.0):
        """Send message. Returns response for request pattern, None for fire."""
        msg_def = A2A_MESSAGE_TYPES.get(msg_type)
        pattern = msg_def.get("pattern", "fire") if msg_def else "fire"

        correlation_id = str(uuid.uuid4())
        message = A2AMessage(
            sender=self.agent_name,
            receiver=receiver,
            type=msg_type,
            payload=payload,
            correlation_id=correlation_id,
        )

        channel = A2A_CHANNELS[f"{self.agent_name}_to_{receiver}"]
        await self.redis.publish(channel, message.model_dump_json())

        if pattern == "request":
            # Wait for response with timeout
            future = asyncio.get_event_loop().create_future()
            self.pending_requests[correlation_id] = future
            try:
                response = await asyncio.wait_for(future, timeout=timeout)
                return response
            except asyncio.TimeoutError:
                del self.pending_requests[correlation_id]
                raise TimeoutError(f"No response for {msg_type} (correlation_id={correlation_id})")

        return None

    async def subscribe(self):
        """Listen for messages from other agents."""
        channel = A2A_CHANNELS[f"{self.agent_name}_to_{self.agent_name}"]
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(channel)

        async for msg in pubsub.listen():
            if msg["type"] == "message":
                data = A2AMessage.model_validate_json(msg["data"])
                await self._handle_message(data)

    async def _handle_message(self, message: A2AMessage):
        """Route message to appropriate handler or resolve pending request."""
        # Check if this is a response to pending request
        if message.correlation_id in self.pending_requests:
            future = self.pending_requests[message.correlation_id]
            future.set_result(message)
            del self.pending_requests[message.correlation_id]
            return

        # Otherwise, call registered handler
        handler = self.handlers.get(message.type)
        if handler:
            response = await handler(message)
            # If handler returns data and message was request, send response
            if response and message.reply_to:
                await self.publish(
                    receiver=message.sender,
                    msg_type=f"{message.type}_result",  # e.g., t2_search_result
                    payload=response,
                    correlation_id=message.correlation_id,
                )

    def register_handler(self, msg_type: str, handler: callable):
        """Register handler for message type."""
        self.handlers[msg_type] = handler
```

### Request-Response Example

```python
# Bay requests T2 search from Evernight
async def search_t2(user_id: str, query: str) -> str:
    try:
        response = await a2a.publish(
            receiver="evernight",
            msg_type="t2_search_request",
            payload={"user_id": user_id, "query": query},
            timeout=5.0  # 5 seconds max
        )
        return response.payload.get("results", "")
    except TimeoutError:
        # Fallback to local T2 (adapter pattern)
        return await local_t2_adapter.search(user_id, query)
```

---

## Concept: "Evernight Agent" = Memory Consolidation

```
┌────────────────────────────────────────────────────────────────────┐
│                    HUMAN MEMORY INSPIRATION                         │
│                                                                     │
│  Human brain consolidates memories during sleep:                   │
│  • Day's experiences → processed at night                          │
│  • Short-term memory → converted to long-term                      │
│  • Unimportant details → forgotten                                 │
│  • Important moments → strengthened                                │
│                                                                     │
│  Bot mimics this with "Evernight Agent":                           │
│  • End of day → Evernight wakes up                                 │
│  • Summarizes all conversations with each user                     │
│  • Stores daily summary to T2 (Qdrant)                             │
│  • Applies TTL decay for natural forgetting                        │
│                                                                     │
└────────────────────────────────────────────────────────────────────┘
```

---

## Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                        MEMORY TIERS                                 │
│                                                                     │
│  T1 (Active Memory) - Redis                                         │
│  ├── Current conversation buffer                                    │
│  ├── TTL: Minutes (session expire)                                 │
│  └── Purpose: "Đang nói gì сейчас"                                 │
│                                                                     │
│  T2 (Episodic Memory) - DAILY SUMMARY                               │
│  ├── Qdrant Vector DB                                              │
│  ├── One entry per user per day                                     │
│  ├── Dream Agent consolidates at night                             │
│  ├── TTL: Days/Weeks (decay over time)                             │
│  └── Purpose: "Hôm nay đã nói gì với user này"                     │
│                                                                     │
│  T3 (Core Memory) - YAML Profile                                    │
│  ├── User facts, preferences                                       │
│  ├── TTL: Permanent                                                │
│  └── Purpose: "Ai là người này"                                    │
│                                                                     │
└────────────────────────────────────────────────────────────────────┘
```

---

## Dream Agent Specification

### Basic Info

```
Agent Name: [CHỐT SAU] 
- Option A: "Dreamer" 
- Option B: "Night Owl" 
- Option C: "Memory Keeper"
- Option D: Vietnamese name: "Thủ Ký", "Ký Giả", "Mộng Du"

Operating Hours: [CHỐT SAU]
- Option A: 00:00 - 02:00 (midnight, like human sleep)
- Option B: 23:00 - 01:00 (end of day)
- Option C: User-configurable time window
```

### Dream Agent Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│                    DREAM AGENT WORKFLOW                          │
│                                                                  │
│  [Trigger Time: 00:00 every day]                                 │
│                                                                  │
│  1. SCAN: Find all users who chatted today                       │
│     └── Query Redis for active sessions                          │
│     └── Filter by date range (today)                             │
│                                                                  │
│  2. EXTRACT: Pull conversation history per user                  │
│     └── Get all messages from T1 buffer                          │
│     └── Include timestamp, role, content                         │
│                                                                  │
│  3. SUMMARIZE: LLM generates daily summary                       │
│     ├── Input: Full conversation log                             │
│     ├── Output: Structured summary                                │
│     │   ├── Topics discussed                                      │
│     │   ├── Key moments                                           │
│     │   ├── Emotions detected                                     │
│     │   ├── New facts discovered → flag for T3                   │
│     └── Model: Lightweight LLM (fast, cheap)                     │
│                                                                  │
│  4. STORE: Save to Qdrant with TTL                               │
│     ├── Create embedding from summary                             │
│     ├── Set TTL based on content importance                       │
│     └── Store: user_id, date, summary, metadata                  │
│                                                                  │
│  5. CLEANUP: Clear T1 buffers                                    │
│     └── Archive or delete old Redis data                          │
│     └── Keep last N hours for continuity                          │
│                                                                  │
│  6. REPORT: Log consolidation results                            │
│     └── Count users processed                                     │
│     └── Count summaries stored                                    │
│     └── Flag errors for review                                    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## T2 Daily Entry Structure

```python
{
    "entry_id": "uuid-xxx",
    "user_id": "726302130318868500",
    "date": "2026-04-21",
    
    # Summary content
    "summary": "Hôm nay user và bot chat về anime Evangelion. User rating 9/10, không thích Shinji. Also user提到 crush tên Hoa.",
    
    "topics": [
        {"topic": "Evangelion anime", "category": "entertainment", "importance": 3},
        {"topic": "Crush Hoa", "category": "relationship", "importance": 4}
    ],
    
    "key_moments": [
        "User debate về ending của Evangelion",
        "User reveal crush tên Hoa, bạn cùng lớp"
    ],
    
    "emotions": ["engaged", "excited"],  # Dominant emotions during chat
    
    "t3_candidates": [
        "User crush tên Hoa"  # Flagged for T3 update
    ],
    
    # TTL metadata
    "importance_score": 3.5,  # Average of topics importance
    "ttl_days": 30,
    "created_at": "2026-04-21T00:30:00Z",
    "last_accessed": "2026-04-21T00:30:00Z",
    
    # Vector embedding
    "embedding": [0.123, 0.456, ...]
}
```

---

## Smart TTL Mechanism (Refresh on Retrieval)

### Core Concept: "Remembering Refreshes Memory"

```
Khi bot retrieve và sử dụng một memory entry:
→ TTL được REFRESH (reset decay)
→ Memory "remembered" → sống lâu hơn
→ Memory không được dùng → decay tự nhiên

Like human memory: Nhắc lại = nhớ lâu hơn
```

### TTL Fields in Entry

```python
{
    "ttl_days": 30,              # Base TTL (by importance)
    "created_at": "2026-04-21T00:30:00Z",
    "last_accessed": "2026-04-21T00:30:00Z",
    "access_count": 0,           # Số lần được retrieve
    "relevance_score": 1.0,      # Current relevance (0-1)
}
```

### Decay Formula

```python
def calculate_relevance(entry, current_time):
    """
    Smart TTL decay với refresh on access.
    
    Formula:
    relevance = importance * decay_factor * access_boost
    
    decay_factor = exp(-days_since_access / ttl_days)
    access_boost = min(1.5, 1 + 0.1 * access_count)  # Max 1.5x boost
    """
    days_since_access = (current_time - entry.last_accessed).days
    
    # Base decay
    decay_factor = math.exp(-days_since_access / entry.ttl_days)
    
    # Access boost (memory used multiple times = stronger)
    access_boost = min(1.5, 1 + 0.1 * entry.access_count)
    
    # Final relevance
    relevance = entry.importance_score * decay_factor * access_boost
    
    return min(1.0, relevance)  # Cap at 1.0
```

### Retrieval Flow với TTL Refresh

```
┌─────────────────────────────────────────────────────────────────┐
│                RETRIEVAL WITH TTL REFRESH                        │
│                                                                  │
│  1. SEARCH: Query Qdrant for relevant entries                   │
│     └── Semantic search: query_embedding vs stored embeddings   │
│     └── Get candidates by user_id                               │
│                                                                  │
│  2. FILTER: Apply TTL decay                                     │
│     └── Calculate relevance for each entry                       │
│     └── Filter by min_relevance threshold (default 0.3)         │
│     └── Sort by relevance descending                            │
│                                                                  │
│  3. RETURN: Top N entries to bot                                │
│     └── Bot receives summaries + relevance scores               │
│     └── Bot may mention memory in response                      │
│                                                                  │
│  4. REFRESH: If bot mentions/uses memory                        │
│     ├── Update last_accessed = now                              │
│     ├── Increment access_count += 1                             │
│     ├── Reset relevance_score = 1.0 (full)                      │
│     └── Write back to Qdrant                                    │
│                                                                  │
│  Example:                                                        │
│  Entry from 20 days ago (decay = 0.5)                           │
│  Bot mentions: "Nhớ hôm trước cậu nói..."                       │
│  → TTL REFRESHED! Entry now has full relevance                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### TTL Behavior Examples

```
Entry: Evangelion discussion (importance 3, TTL 30 days)

Scenario A: Never retrieved
├── Day 1:  relevance = 1.0  ✅ Fresh
├── Day 15: relevance = 0.5  ⚠️ Fading  
├── Day 30: relevance = 0.1  ❌ Almost forgotten
└── Day 60: relevance = 0.0  ❌ Forgotten (filtered out)

Scenario B: Retrieved on Day 15
├── Day 1:  relevance = 1.0  ✅ Fresh
├── Day 15: relevance = 0.5  Bot retrieves & mentions
│   └── REFRESH! last_accessed = Day 15
│   └── access_count = 1
│   └── relevance reset to 1.0
├── Day 16: relevance = 0.97 ✅ Strong (just refreshed)
├── Day 45: relevance = 0.5  ⚠️ Fading again
└── ...

Scenario C: Retrieved multiple times
├── Day 1:  created, access_count = 0
├── Day 10: retrieved → access_count = 1, boost = 1.1
├── Day 20: retrieved → access_count = 2, boost = 1.2
├── Day 30: retrieved → access_count = 3, boost = 1.3
└── Even with decay, access_boost makes it last longer
```

### TTL by Importance

```
Base TTL (before any retrieval):
- importance 5 → TTL 90 days (relationship, personal milestone)
- importance 4 → TTL 60 days 
- importance 3 → TTL 30 days (entertainment, hobbies)
- importance 2 → TTL 14 days
- importance 1 → TTL 7 days  (casual chat)

With access_boost (max 1.5x):
- importance 3, accessed 5 times → effective TTL = 30 * 1.5 = 45 days
```

### Implementation: TTL Refresh Trigger

```python
# Option A: Auto-refresh on retrieval
async def search_and_refresh(query, user_id, min_relevance=0.3):
    entries = await qdrant.search(query_embedding, user_id)
    
    relevant_entries = []
    for entry in entries:
        relevance = calculate_relevance(entry, now)
        if relevance >= min_relevance:
            # AUTO REFRESH on every retrieval
            entry.last_accessed = now
            entry.access_count += 1
            await qdrant.update(entry)
            
            relevant_entries.append(entry)
    
    return relevant_entries

# Option B: Manual refresh (bot decides)
async def search_memory(query, user_id):
    entries = await qdrant.search(query_embedding, user_id)
    return entries  # No auto-refresh

async def refresh_memory(entry_id):
    """Bot calls this when it decides to 'remember'"""
    entry = await qdrant.get(entry_id)
    entry.last_accessed = now
    entry.access_count += 1
    await qdrant.update(entry)

# Recommended: Option B (manual)
# Bot has agency - only refresh if bot actually USES the memory
```

---

## Document Structure & Retrieval Optimization

### Problem: One Big Entry vs Multiple Chunks

```
┌─────────────────────────────────────────────────────────────────┐
│                    DOCUMENT STRUCTURE DILEMMA                    │
│                                                                  │
│  Current proposal: One entry per user per day                   │
│  ┌─────────────────────────────────────────────────┐            │
│  │ Entry: "2026-04-21"                              │            │
│  │ - Summary: long text (3 topics mixed)            │            │
│  │ - Embedding: ONE vector for whole entry          │            │
│  │ - Topics: [Evangelion, Crush Hoa, Game]          │            │
│  └─────────────────────────────────────────────────┘            │
│                                                                  │
│  ❌ Problem: Semantic search diluted                            │
│  • Query: "anime" → matches "Evangelion" part                   │
│  • But embedding includes "Crush Hoa" noise                     │
│  • Retrieval accuracy decreased                                 │
│                                                                  │
│  ❌ Problem: Cannot filter by specific topic                    │
│  • Want: "Tìm chat về Evangelion"                               │
│  • Result: Returns whole day entry                              │
│  • Bot receives irrelevant info (Crush Hoa)                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

### Option A: Single Entry (Daily Summary)

```python
# ONE entry per day, all topics in one
{
    "entry_id": "day-2026-04-21-user-123",
    "user_id": "123",
    "date": "2026-04-21",
    
    "summary": "Chat về Evangelion (9/10, không thích Shinji). User reveal crush Hoa. Cũng nói về game Valorant.",
    
    "topics": ["Evangelion", "Crush Hoa", "Valorant"],  # Metadata only
    "categories": ["entertainment", "relationship", "entertainment"],
    
    "embedding": [0.123, ...],  # ONE vector for whole summary
}
```

**Pros:**
- Simple storage
- Easy retrieval by date
- Less Qdrant operations

**Cons:**
- ❌ Semantic dilution
- ❌ Cannot target specific topic
- ❌ Mixed relevance scores

---

### Option B: Topic-Level Chunks (Granular)

```python
# MULTIPLE entries per day, one per topic
[
    {
        "chunk_id": "topic-evangelion-2026-04-21-user-123",
        "user_id": "123",
        "date": "2026-04-21",
        "parent_day_id": "day-2026-04-21-user-123",  # Link to parent
        
        "topic": "Evangelion anime",
        "category": "entertainment",
        "importance": 3,
        
        "content": "User chat về anime Evangelion, rating 9/10, không thích character Shinji, debate về ending.",
        
        "embedding": [0.456, ...],  # Vector for THIS topic only
    },
    
    {
        "chunk_id": "topic-crush-2026-04-21-user-123",
        "user_id": "123",
        "date": "2026-04-21",
        "parent_day_id": "day-2026-04-21-user-123",
        
        "topic": "Crush Hoa",
        "category": "relationship",
        "importance": 4,
        
        "content": "User reveal crush tên Hoa, bạn cùng lớp, đã crush 2 tháng.",
        
        "embedding": [0.789, ...],  # Separate vector
    },
    
    {
        "chunk_id": "topic-valorant-2026-04-21-user-123",
        "user_id": "123",
        "date": "2026-04-21",
        "parent_day_id": "day-2026-04-21-user-123",
        
        "topic": "Valorant game",
        "category": "entertainment",
        "importance": 2,
        
        "content": "User chơi Valorant, rank Gold, thích agent Jett.",
        
        "embedding": [0.321, ...],
    }
]
```

**Pros:**
- ✅ Precise semantic matching
- ✅ Can filter by category/topic
- ✅ Better retrieval accuracy
- ✅ TTL per topic (different decay)

**Cons:**
- More Qdrant entries (3x-5x)
- Need parent-child linking
- More embedding operations

---

### Option C: Hybrid (Day Summary + Topic Chunks)

```python
# BOTH: Day entry (overview) + Topic chunks (detail)

# Parent entry (day overview)
{
    "entry_id": "day-2026-04-21-user-123",
    "user_id": "123",
    "date": "2026-04-21",
    "type": "day_summary",
    
    "overview": "3 topics discussed: Evangelion, Crush Hoa, Valorant",
    "topics_count": 3,
    
    "children": [
        "topic-evangelion-2026-04-21-user-123",
        "topic-crush-2026-04-21-user-123",
        "topic-valorant-2026-04-21-user-123"
    ],
    
    "embedding": [0.111, ...],  # Overview embedding (optional)
}

# Child entries (topic chunks)
# (Same as Option B)
```

**Pros:**
- ✅ Overview for quick scan
- ✅ Detail for precise search
- ✅ Hierarchical retrieval

**Cons:**
- Most complex structure
- Need both queries sometimes

---

### Retrieval Strategies

```
┌─────────────────────────────────────────────────────────────────┐
│                    RETRIEVAL USE CASES                           │
│                                                                  │
│  Use Case 1: "User đã nói gì về anime?"                         │
│  ┌─────────────────────────────────────────────────┐            │
│  │ Option A: Search whole entries → fuzzy match     │            │
│  │ Option B: Filter category=entertainment → precise│            │
│  │ Option C: Get children → specific anime chunk    │            │
│  └─────────────────────────────────────────────────┘            │
│  → Option B/C better for precision                             │
│                                                                  │
│  Use Case 2: "Hôm nay user nói gì?"                             │
│  ┌─────────────────────────────────────────────────┐            │
│  │ Option A: Get today's entry → all topics         │            │
│  │ Option B: Get all chunks for today → many        │            │
│  │ Option C: Get day entry → overview               │            │
│  └─────────────────────────────────────────────────┘            │
│  → Option A/C better for overview                              │
│                                                                  │
│  Use Case 3: "User có crush ai?"                                │
│  ┌─────────────────────────────────────────────────┐            │
│  │ Option A: Search → may miss if buried in text    │            │
│  │ Option B: Filter category=relationship → find!   │            │
│  │ Option C: Get relationship chunks → all crushes  │            │
│  └─────────────────────────────────────────────────┘            │
│  → Option B/C essential for factual queries                    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

### Qdrant Schema Design

```python
# Collection: "episodic_memory"

# Payload structure (Option B - Recommended)
{
    # Identity fields
    "chunk_id": str,           # Primary key
    "user_id": str,            # Filter by user
    "date": str,               # Filter by date (YYYY-MM-DD)
    
    # Content fields
    "topic": str,              # Topic title (for display)
    "category": str,           # entertainment | relationship | work_study | casual | daily_mood
    "content": str,            # Full text content
    
    # Importance & TTL
    "importance": int,         # 1-5
    "ttl_days": int,           # Base TTL
    "created_at": datetime,
    "last_accessed": datetime,
    "access_count": int,
    
    # Parent linking (for Option C)
    "parent_day_id": str,      # Link to day summary
    "type": str,               # "day_summary" | "topic_chunk"
    
    # Embedding (stored separately in Qdrant vector)
    # vector: [float, ...]
}
```

---

### Qdrant Filtering Optimization

```python
# Efficient retrieval with filters

async def search_memory(query, user_id, filters=None):
    """
    Search with multiple filter options.
    """
    query_embedding = await embedding_service.embed(query)
    
    # Build filter conditions
    filter_conditions = [
        FieldCondition(key="user_id", match=MatchValue(value=user_id))
    ]
    
    if filters:
        # Category filter
        if "category" in filters:
            filter_conditions.append(
                FieldCondition(key="category", match=MatchValue(value=filters["category"]))
            )
        
        # Date range filter
        if "date_from" in filters:
            filter_conditions.append(
                FieldCondition(key="date", range=Range(gte=filters["date_from"]))
            )
        
        # Importance threshold
        if "min_importance" in filters:
            filter_conditions.append(
                FieldCondition(key="importance", range=Range(gte=filters["min_importance"]))
            )
        
        # TTL relevance (calculated field)
        if "min_relevance" in filters:
            # Need post-filtering (calculated at runtime)
            pass
    
    # Query Qdrant
    results = await qdrant_client.search(
        collection_name="episodic_memory",
        query_vector=query_embedding,
        query_filter=Filter(must=filter_conditions),
        limit=10
    )
    
    # Post-process: Apply TTL decay
    for result in results:
        relevance = calculate_relevance(result.payload, now)
        result.payload["relevance"] = relevance
    
    # Filter by TTL relevance
    if "min_relevance" in filters:
        results = [r for r in results if r.payload["relevance"] >= filters["min_relevance"]]
    
    return results
```

---

### Embedding Strategy

```
┌─────────────────────────────────────────────────────────────────┐
│                    EMBEDDING APPROACHES                          │
│                                                                  │
│  Approach 1: Embed full content                                 │
│  ├── Embed: "User chat về Evangelion, rating 9/10..."          │
│  ├── Pros: Complete context                                     │
│  └── Cons: Diluted semantics                                    │
│                                                                  │
│  Approach 2: Embed topic + key points only                      │
│  ├── Embed: "Evangelion anime + rating 9/10 + dislikes Shinji" │
│  ├── Pros: Focused semantics                                    │
│  └── Cons: Missing nuance                                       │
│                                                                  │
│  Approach 3: Multi-vector (content + metadata)                  │
│  ├── Vector 1: Content embedding                                │
│  ├── Vector 2: Topic/category embedding (sparse)               │
│  ├── Pros: Hybrid matching                                      │
│  └── Cons: Complex storage, Qdrant multi-vector support?        │
│                                                                  │
│  Recommended: Approach 2 (focused)                              │
│  → Better semantic matching for queries                         │
│  → Topic + key_moments combined for embedding input             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

### Questions to Resolve (Document Structure)

1. **Which option: A, B, or C?**
   - Option A: Simple, but retrieval imprecise
   - Option B: Granular, better search, more entries
   - Option C: Hybrid, most complex

2. **Topic extraction: How granular?**
   - Every topic mentioned?
   - Only topics with ≥2 exchanges?
   - Only topics with importance ≥2?

3. **Category taxonomy: Fixed or dynamic?**
   - Fixed: entertainment, relationship, work_study, casual, daily_mood
   - Dynamic: Bot assigns categories freely

4. **Parent-child linking: Needed?**
   - For Option C: Yes, essential
   - For Option B: Optional, for grouping

5. **Embedding input: What to embed?**
   - Full content?
   - Topic + summary only?
   - Include metadata in embedding?

---

### Preliminary Recommendation

```
┌─────────────────────────────────────────────────────────────────┐
│                  RECOMMENDED APPROACH                            │
│                                                                  │
│  Document Structure: Option B (Topic-Level Chunks)              │
│  ├── One entry per topic per day                                │
│  ├── Better semantic precision                                  │
│  ├── Easier category-based filtering                            │
│  └── TTL per topic (relationship lasts longer than casual)      │
│                                                                  │
│  Embedding Strategy: Approach 2 (Focused)                      │
│  ├── Embed: topic + key_points                                  │
│  ├── Input: "Evangelion anime: rating 9/10, dislikes Shinji"   │
│  └── Better query matching                                      │
│                                                                  │
│  Category Taxonomy: Fixed (5 categories)                        │
│  ├── entertainment, relationship, work_study, casual, daily_mood│
│  └── Easy filtering, predictable                                │
│                                                                  │
│  Retrieval: Hybrid query + filter                               │
│  ├── Semantic search (embedding)                                │
│  ├── Category filter (metadata)                                 │
│  ├── TTL decay (post-processing)                                │
│  └── Importance boost                                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Implementation Tasks

### Phase 0: Refactor to Twin Souls Structure (FOUNDATION)

#### Phase 0a: Create Structure + Shared Layer (NO BREAKING CHANGES)
- [ ] Create `src/agents/` directory structure (empty folders)
- [ ] Create `src/agents/shared/`:
  - [ ] `shared/embedding/` - Copy (not move) embedding service
  - [ ] `shared/qdrant/` - Copy Qdrant connection helper
  - [ ] `shared/models/` - Create base models
  - [ ] `shared/tools/` - Move MCP tools (both agents use)
  - [ ] `shared/config.py` - Shared env vars (Redis, Qdrant URLs)
- [ ] Create `src/agents/shared/a2a/`:
  - [ ] `channels.py` - Redis channel definitions
  - [ ] `messages.py` - A2A message schema (ALL message types)
  - [ ] `protocol.py` - A2A base class with request-response pattern
- [ ] Create `src/agents/bay/` structure (keep current src/ working)
  - [ ] `bay/__init__.py` - Import aliases to current modules
  - [ ] `bay/config.py` - Bay-specific config wrapper
- [ ] Tests pass with current structure unchanged

#### Phase 0b: Gradual Migration (ONE MODULE AT A TIME)
- [ ] Move `src/cogs/` → `src/agents/bay/discord/` (update imports)
- [ ] Move `src/services/chat_coordinator.py` → `bay/services/`
- [ ] Move T1 memory modules → `bay/services/t1_memory/`
- [ ] Move T3 memory modules → `bay/services/t3_memory/`
- [ ] Move LLM services → `bay/services/llm/`
- [ ] **Keep EpisodicMemory WORKING** (don't remove yet)
- [ ] Each migration: tests pass before next

#### Phase 0c: Create T2RetrievalAdapter (BRIDGE)
- [ ] Create `shared/t2_adapter.py`:
  ```python
  class T2RetrievalAdapter:
      """Bridge between old EpisodicManager and Evernight."""

      def __init__(self, mode: Literal["local", "a2a"]):
          self.mode = mode
          self.local_manager = None  # EpisodicManager (old)
          self.a2a_client = None     # A2A client (new)

      async def search(self, user_id, query) -> str:
          if self.mode == "local":
              return await self.local_manager.retrieve_past_context(...)
          else:
              return await self.a2a_client.request_t2_search(...)
  ```
- [ ] Update `SearchMemoryTool` to use adapter
- [ ] Update `MemoryManager` to use adapter
- [ ] Tests pass with adapter in "local" mode

### Phase 1: Create Evernight Agent Service
- [ ] Create `src/agents/evernight/` directory
- [ ] Create `EvernightAgent` class (`evernight/agent.py`)
- [ ] Create `evernight/config.py` (own LLM config)
- [ ] Create `evernight/entrypoint.py` (independent process)
- [ ] Implement **Dual Trigger** mechanism:
  - [ ] Scheduled trigger: 11PM-6AM window (cron/APScheduler)
  - [ ] Token threshold trigger: A2A message from Bay
- [ ] Create `evernight/a2a/`:
  - [ ] `subscriber.py` - Listen for A2A messages from Bay
  - [ ] `publisher.py` - Send A2A messages to Bay

### Phase 2: T2 Memory Consolidation
- [ ] Create `evernight/services/t2_memory/`:
  - [ ] `consolidation/` - Summary generation
  - [ ] `storage/` - Qdrant operations
  - [ ] `retrieval/` - Search + TTL refresh
- [ ] Create prompt template for topic-level summary
- [ ] Implement multi-user batch processing
- [ ] Extract topics with categories
- [ ] Handle edge cases (empty day, long conversations)

### Phase 3: Qdrant Storage (Topic-Level Chunks)
- [ ] Create new `TopicChunkRecord` model in `shared/models/`
- [ ] New fields: `topic`, `category`, `importance`, `ttl_days`, `last_accessed`, `access_count`
- [ ] Implement TTL decay calculation
- [ ] Implement refresh on retrieval mechanism
- [ ] Update Qdrant schema in `shared/qdrant/`

### Phase 4: A2A Integration
- [ ] Update Bay to send `t1_overflow` A2A message
- [ ] Evernight handler for `t1_overflow` → trigger consolidation
- [ ] Evernight sends `t2_consolidated` notification
- [ ] Bay handler for `t2_consolidated` (optional)
- [ ] Add `t2_search_request` / `t2_search_result` for retrieval

### Phase 5: Cleanup & Testing
- [ ] Remove old `EpisodicManager` from Bay
- [ ] Update `SearchMemoryTool` to use A2A for T2 search
- [ ] Add error handling and retry logic
- [ ] Create monitoring/logging for Evernight runs
- [ ] Test full flow: T1 overflow → A2A → Evernight → T2 storage

---

## Evernight Prompt Template (Draft)

```markdown
# EVERNIGHT - DAILY SUMMARY PROMPT

Bạn là Evernight Agent, nhiệm vụ tóm tắt cuộc trò chuyện trong ngày.

INPUT: Lịch sử chat với user [USER_ID] ngày [DATE]

OUTPUT FORMAT (JSON):
{
  "summary": "Tóm tắt 1-2 câu về nội dung chính",
  "topics": [
    {"topic": "...", "category": "...", "importance": 1-5}
  ],
  "key_moments": ["moment 1", "moment 2"],
  "emotions": ["engaged", "casual", ...],
  "t3_candidates": ["info cần lưu vào T3"]
}

QUY TẮC:
1. Topics: Chỉ lấy chủ đề có chiều sâu (≥2 exchanges)
2. Importance: 5 = relationship/personal, 3 = entertainment, 1 = casual
3. T3 candidates: Info về user identity (tên, tuổi, nghề nghiệp, quan hệ)
4. Emotions: Dominant emotion(s) trong cuộc chat
5. Summary: Ngắn gọn, capture essence of the day

CHAT HISTORY:
[INSERT FULL CONVERSATION LOG]
```

---

## Scheduling Options

### Option A: Cron Job (Simple)

```python
# Using APScheduler or similar
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()
scheduler.add_job(
    dream_agent.run_daily_consolidation,
    trigger='cron',
    hour=0, minute=0  # 00:00 every day
)
scheduler.start()
```

### Option B: Discord Event (Integrated)

```python
# Using Discord.py scheduled event
# Bot creates recurring event "Dream Agent Consolidation"
# Runs as background task during event window
```

### Option C: External Trigger (Flexible)

```python
# Manual trigger via admin command
# Or external cron (system cron, Kubernetes cron job)
# API endpoint: POST /admin/dream-agent/run
```

---

## Resolved Questions (Archive)

| # | Question | Resolution |
|---|----------|------------|
| 1 | Agent Name? | **Evernight** |
| 2 | Operating Hours? | **Dual Trigger**: 11PM-6AM + Token threshold |
| 3 | T3 Handling? | **Tách biệt** - Evernight only T2, T3 by main bot |
| 4 | Model config? | **Separate** - fallback independent |
| 5 | T2 Strategy? | **Replace** current T2 structure |
| 6 | Error Handling? | Retry mechanism + manual trigger recovery |

---

## Timeline

| Phase | Tasks | Est. Complexity |
|-------|-------|-----------------|
| Phase 0 | Refactor to Twin Souls structure | High (foundation) |
| Phase 1 | Evernight Agent + Dual Trigger + A2A | Medium |
| Phase 2 | T2 Memory Consolidation | Medium |
| Phase 3 | Qdrant Storage (Topic-Level Chunks) | Low |
| Phase 4 | A2A Integration | Medium |
| Phase 5 | Cleanup & Testing | Low |

**Recommended:** Phase 0a-0c in 1-2 sessions, then Phase 1-5 incrementally

---

## Evaluation & Missing Considerations (Self + Agent Review)

### Issues Identified & Fixed ✅

| Issue | Fix Applied |
|-------|-------------|
| Phase 0 too aggressive | Split into 0a (create), 0b (migrate), 0c (adapter) |
| No A2A request-response | Added correlation_id + timeout pattern |
| Missing A2A message types | Added health_check, error_notification, manual_trigger |
| Old T2 breaks before new ready | T2RetrievalAdapter with "local" fallback |
| Dream Agent → Evernight rename | Updated all references |

### Still Missing (Define During Implementation)

| Category | Missing Item | Priority |
|----------|--------------|----------|
| **Topic Extraction** | Precise criteria for "depth ≥2 exchanges" | High |
| **Topic Extraction** | Who assigns importance score? (LLM prompt needed) | High |
| **Qdrant Migration** | Plan for existing EpisodicRecords → TopicChunks | Medium |
| **Deployment** | Docker config: separate container? shared? | Medium |
| **Testing** | A2A mock, TTL decay tests, adapter tests | Medium |
| **Error Handling** | Evernight retry policy (how many retries? backoff?) | Low |

### Security Considerations

- Redis A2A: No auth currently → add password when production
- Qdrant API key: Both agents need access → shared config
- A2A message validation: Pydantic schema enforces structure

---

## Notes

### Twin Souls Architecture
- **Bay** = Main Discord agent (current bot refactored)
- **Evernight** = Twin agent (T2 memory + future functions)
- **A2A** = Redis Pub/Sub for inter-agent communication
- **Shared** = Qdrant, Embedding, Tools, Models

### T2 Memory
- Dual trigger: Scheduled (11PM-6AM) + A2A message from Bay (T1 overflow)
- Separate model config for fallback independence
- Tách biệt từ T3 - Evernight chỉ lo T2
- Topic-Level Chunks (one entry per topic per day)
- TTL decay + refresh on retrieval

### Future Functions (Evernight)
- Error recovery/fix for Bay
- Analytics & reporting
- Maintenance tasks
- (Incremental - define later)

---

**Ready for Implementation** ✅

Architecture finalized on 22/04/2026.