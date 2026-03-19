# 🧩 Relationship Graph System - Thiết kế Chi tiết

## 📋 Mục lục
1. [Tổng quan & Vấn đề hiện tại](#1-tổng-quan--vấn-đề-hiện-tại)
2. [Kiến trúc Đề xuất](#2-kiến-trúc-đề-xuất)
3. [Cấu trúc Dữ liệu](#3-cấu-trúc-dữ-liệu)
4. [Event System Integration](#4-event-system-integration)
5. [LLM Prompts cho Relationship Extraction](#5-llm-prompts-cho-relationship-extraction)
6. [API & Interface Design](#6-api--interface-design)
7. [Implementation Roadmap](#7-implementation-roadmap)

---

## 1. Tổng quan & Vấn đề hiện tại

### 1.1 Vấn đề với Relationship System cũ

```python
# Hiện tại trong UserProfile (core_memory/models.py):
relationships: List[str] = Field(
    default_factory=list, 
    description="Gia đình, bạn bè, thú cưng, tình trạng hôn nhân"
)
# Ví dụ data: ["Có bạn tên Nam", "Đã kết hôn", "Thích crush tên Lan"]
```

**❌ Điểm yếu:**

| Vấn đề | Mô tả |
|--------|-------|
| **Flat List** | Không có cấu trúc graph, không biết A→B và B→A có thể khác nhau |
| **Không có Weight** | Không đo lường được mức độ thân thiết (intimacy score) |
| **Không track Interactions** | Không biết A và B đã chat bao nhiêu lần, mention nhau thế nào |
| **Không có Sentiment** | Không biết A nói về B với thái độ positive/negative |
| **Không có Timestamp** | Không biết mối quan hệ thay đổi theo thời gian ra sao |
| **Không có Directionality** | A coi B là "bạn thân" nhưng B có thể coi A là "quen biết" |

### 1.2 Mục tiêu hệ thống mới

**Sơ đồ luồng xử lý:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              INPUT LAYER                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                │
│    │  Tin nhắn    │    │   Mentions   │    │  Reactions   │                │
│    │   User       │    │   @user      │    │   👍❤️😂     │                │
│    └──────┬───────┘    └──────┬───────┘    └──────┬───────┘                │
│           │                   │                   │                        │
└───────────┼───────────────────┼───────────────────┼────────────────────────┘
            │                   │                   │
            ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            PROCESSING LAYER                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│    ┌──────────────────────────────────────────────────────────────┐        │
│    │                    LLM Extraction Engine                      │        │
│    │  • Phân tích sentiment                                       │        │
│    │  • Trích xuất relationship type                              │        │
│    │  • Tính intimacy score                                       │        │
│    └────────────────────────────┬─────────────────────────────────┘        │
│                                 │                                           │
│                                 ▼                                           │
│    ┌──────────────────────────────────────────────────────────────┐        │
│    │                    Scoring Engine                             │        │
│    │  • Interaction frequency scoring                              │        │
│    │  • Temporal decay calculation                                 │        │
│    │  • Confidence weighting                                       │        │
│    └────────────────────────────┬─────────────────────────────────┘        │
│                                 │                                           │
│                                 ▼                                           │
│    ┌──────────────────────────────────────────────────────────────┐        │
│    │                  RELATIONSHIP GRAPH                           │        │
│    │                                                               │        │
│    │     User A ──────[friend, 0.9]──────▶ User B                 │        │
│    │       ▲                                  │                    │        │
│    │       │                                  │                    │        │
│    │     [acquaintance, 0.3]                  │                    │        │
│    │       │                                  ▼                    │        │
│    │     User C ◀─────[colleague, 0.5]──── User D                 │        │
│    │                                                               │        │
│    └──────────────────────────────────────────────────────────────┘        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              OUTPUT LAYER                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                │
│    │    Query     │    │   Social     │    │   Context    │                │
│    │ Relationships│    │   Insights   │    │  for LLM     │                │
│    └──────────────┘    └──────────────┘    └──────────────┘                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**✅ Mục tiêu:**
1. **Graph-based relationships** với directed edges và weighted connections
2. **Real-time tracking** interactions giữa các users
3. **Sentiment-aware** - biết user nói về người khác với thái độ gì
4. **Temporal tracking** - mối quan hệ thay đổi theo thời gian
5. **Integration với Memory 3 tầng** hiện có

---

## 2. Kiến trúc Đề xuất

### 2.1 Vị trí trong hệ thống Memory 3 tầng

**Sơ đồ kiến trúc tổng thể:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        MEMORY SYSTEM ARCHITECTURE                            │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  TẦNG 1: ACTIVE MEMORY (RAM)                                                │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                                                                     │   │
│  │   ActiveMemoryService          EventDispatcher                     │   │
│  │   ┌─────────────────┐         ┌─────────────────┐                  │   │
│  │   │ • Đánh giá msg  │────────▶│ • Emit events   │                  │   │
│  │   │ • Đếm token     │         │ • Pub/Sub       │                  │   │
│  │   │ • Phát hiện     │         └────────┬────────┘                  │   │
│  │   │   relationship  │                  │                           │   │
│  │   └─────────────────┘                  │                           │   │
│  │                                        │                           │   │
│  └────────────────────────────────────────┼───────────────────────────┘   │
│                                           │                                │
└───────────────────────────────────────────┼────────────────────────────────┘
                                            │
                    ┌───────────────────────┼───────────────────────┐
                    │                       │                       │
                    ▼                       ▼                       ▼
┌───────────────────────────┐ ┌───────────────────────┐ ┌─────────────────────┐
│  TẦNG 2: EPISODIC MEMORY  │ │  RELATIONSHIP GRAPH   │ │  TẦNG 3: CORE MEM   │
│  ┌─────────────────────┐  │ │  ┌─────────────────┐  │ │  ┌───────────────┐  │
│  │                     │  │ │  │                 │  │ │  │               │  │
│  │  EpisodicManager    │  │ │  │ GraphManager    │  │ │  │ CoreManager   │  │
│  │  ┌───────────────┐  │  │ │  │ ┌─────────────┐ │  │ │  │ ┌───────────┐ │  │
│  │  │EventExtractor │  │  │ │  │ │ Extractor   │ │  │ │  │ │SmartUpdate│ │  │
│  │  └───────────────┘  │  │ │  │ └─────────────┘ │  │ │  │ └───────────┘ │  │
│  │  ┌───────────────┐  │  │ │  │ ┌─────────────┐ │  │ │  │ ┌───────────┐ │  │
│  │  │ VectorEngine  │  │  │ │  │ │ Storage     │ │  │ │  │ │ Storage   │ │  │
│  │  └───────────────┘  │  │ │  │ └─────────────┘ │  │ │  │ └───────────┘ │  │
│  │  ┌───────────────┐  │  │ │  │ ┌─────────────┐ │  │ │  │               │  │
│  │  │ VectorDB      │  │  │ │  │ │InteractionTracker│ │  │ │ UserProfile   │  │
│  │  └───────────────┘  │  │ │  │ └─────────────┘ │  │ │  │               │  │
│  │                     │  │ │  │                 │  │ │  │               │  │
│  └─────────────────────┘  │ │  └─────────────────┘  │ │  └───────────────┘  │
│                           │ │                       │ │                     │
│  • Vector embeddings      │ │  • Graph edges        │ │  • User profile     │
│  • Semantic search        │ │  • Interaction events │ │  • Core facts       │
│  • Long-term memory       │ │  • Sentiment tracking │ │  • Relationships    │
│                           │ │                       │ │                     │
└───────────────────────────┘ └───────────────────────┘ └─────────────────────┘
        │                              │                        │
        │                              │                        │
        └──────────────────────────────┼────────────────────────┘
                                       │
                                       ▼
                    ┌─────────────────────────────────────┐
                    │         ChatCoordinator            │
                    │   (Orchestrates all components)    │
                    └─────────────────────────────────────┘
```

### 2.2 Components chi tiết

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    RELATIONSHIP GRAPH COMPONENTS                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                 RelationshipGraphManager (Facade)                    │  │
│   │                                                                      │  │
│   │   • Điều phối toàn bộ operations                                    │  │
│   │   • Public API cho ChatCoordinator                                  │  │
│   │   • Event handlers cho EventDispatcher                              │  │
│   │                                                                      │  │
│   └──────────────────────────────┬──────────────────────────────────────┘  │
│                                  │                                          │
│          ┌───────────────────────┼───────────────────────┐                 │
│          │                       │                       │                 │
│          ▼                       ▼                       ▼                 │
│   ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐         │
│   │   Extractor     │   │    Storage      │   │InteractionTracker│         │
│   │                 │   │                 │   │                 │         │
│   │ • LLM-based     │   │ • JSON/Vector   │   │ • Mention track │         │
│   │   extraction    │   │   DB storage    │   │ • Reply track   │         │
│   │ • Sentiment     │   │ • CRUD ops      │   │ • Reaction track│         │
│   │   analysis      │   │ • Search        │   │ • Stats update  │         │
│   │ • Type classify │   │                 │   │                 │         │
│   │                 │   │                 │   │                 │         │
│   └─────────────────┘   └─────────────────┘   └─────────────────┘         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.3 Component Responsibilities

| Component | Trách nhiệm |
|-----------|-------------|
| **RelationshipGraphManager** | Facade điều phối toàn bộ relationship operations |
| **RelationshipExtractor** | Dùng LLM để extract relationship từ conversation |
| **RelationshipStorage** | Lưu trữ graph data (JSON/Vector DB) |
| **InteractionTracker** | Track real-time interactions (mentions, replies, reactions) |

---

## 3. Cấu trúc Dữ liệu

### 3.1 Entity Relationship Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    RELATIONSHIP DATA MODEL                                   │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────┐       ┌─────────────────────────┐
│     USER_PROFILE        │       │    RELATIONSHIP_EDGE    │
│  (Existing in T3)       │       │      (NEW)              │
├─────────────────────────┤       ├─────────────────────────┤
│ user_id (PK)           │       │ id (PK)                 │
│ name                   │       │ source_user_id (FK)     │───┐
│ demographics           │       │ target_user_id (FK)     │───┼──┐
│ occupation             │       │ target_display_name     │   │  │
│ relationships []       │◀──────│ relationship_type       │   │  │
│ interests []           │       │ intimacy_score (0-1)    │   │  │
│ goals_and_plans []     │       │ sentiment               │   │  │
│ preferences []         │       │ confidence              │   │  │
│ constraints []         │       │ total_interactions      │   │  │
│ other_facts []         │       │ mentions_given          │   │  │
└─────────────────────────┘       │ mentions_received       │   │  │
         │                        │ last_interaction_at    │   │  │
         │                        │ relationship_facts []  │   │  │
         │                        │ context_snippets []    │   │  │
         │                        │ created_at             │   │  │
         │                        │ updated_at             │   │  │
         │                        │ decay_factor           │   │  │
         │                        └─────────────────────────┘   │  │
         │                                     │                │  │
         │                                     │                │  │
         │                        ┌────────────┴────────────┐   │  │
         │                        │                         │   │  │
         │                        ▼                         ▼   │  │
         │              ┌─────────────────────┐   ┌─────────────────┐
         │              │  INTERACTION_EVENT  │   │  USER_PROFILE   │
         │              │       (NEW)         │   │   (Target)      │
         │              ├─────────────────────┤   ├─────────────────┤
         │              │ id (PK)             │   │ user_id (PK)    │
         │              │ source_user_id (FK) │──▶│ name            │
         │              │ target_user_id (FK) │──▶│ ...             │
         │              │ interaction_type    │   └─────────────────┘
         │              │ content_snippet     │
         │              │ sentiment (-1 to 1) │
         │              │ channel_id          │
         │              │ message_id          │
         │              │ timestamp           │
         │              └─────────────────────┘
         │                         │
         │                         │
         └─────────────────────────┘
```

### 3.2 Models (Python Code)

```python
# src/services/relationship_graph/models.py

from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class RelationshipType(str, Enum):
    """Phân loại mối quan hệ"""
    FAMILY = "family"           # Gia đình
    ROMANTIC = "romantic"       # Lover, crush, ex
    FRIEND = "friend"           # Bạn bè
    ACQUAINTANCE = "acquaintance"  # Quen biết
    COLLEAGUE = "colleague"     # Đồng nghiệp
    STRANGER = "stranger"       # Người lạ
    RIVAL = "rival"             # Đối thủ
    MENTOR = "mentor"           # Mentor/mentee
    PET = "pet"                 # Thú cưng


class SentimentType(str, Enum):
    """Sentiment của relationship"""
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    MIXED = "mixed"


class InteractionType(str, Enum):
    """Loại interaction"""
    MENTION = "mention"
    REPLY = "reply"
    REACTION = "reaction"
    DM = "direct_message"
    CONVERSATION = "conversation"


class RelationshipEdge(BaseModel):
    """
    Cạnh có hướng trong Relationship Graph.
    Đại diện cho cách User A nhìn nhận User B.
    """
    # Identifiers
    id: str = Field(..., description="Unique edge ID")
    source_user_id: str = Field(..., description="User A - người có nhận xét")
    target_user_id: str = Field(..., description="User B - người được nhận xét")
    target_display_name: Optional[str] = Field(None, description="Tên hiển thị của B")
    
    # Relationship Classification
    relationship_type: RelationshipType = Field(
        default=RelationshipType.ACQUAINTANCE,
        description="Phân loại mối quan hệ"
    )
    
    # Quantitative Metrics
    intimacy_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Điểm thân thiết (0=người lạ, 1=người thân nhất)"
    )
    sentiment: SentimentType = Field(
        default=SentimentType.NEUTRAL,
        description="Thái độ cảm xúc"
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Độ tin cậy của prediction"
    )
    
    # Interaction Stats
    total_interactions: int = Field(default=0, description="Tổng số tương tác")
    mentions_given: int = Field(default=0, description="Số lần A mention B")
    mentions_received: int = Field(default=0, description="Số lần B mention A")
    last_interaction_at: Optional[datetime] = Field(None)
    
    # Qualitative Data
    relationship_facts: List[str] = Field(
        default_factory=list,
        description="Các fact về mối quan hệ"
    )
    context_snippets: List[str] = Field(
        default_factory=list,
        description="Các đoạn chat context"
    )
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    decay_factor: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Hệ số suy giảm theo thời gian"
    )


class InteractionEvent(BaseModel):
    """
    Một interaction event giữa 2 users.
    """
    id: str = Field(...)
    source_user_id: str
    target_user_id: str
    interaction_type: InteractionType
    content_snippet: Optional[str] = Field(None)
    sentiment: Optional[float] = Field(None, ge=-1.0, le=1.0)
    channel_id: Optional[str] = None
    message_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class RelationshipGraphSnapshot(BaseModel):
    """
    Snapshot của relationship graph cho một user.
    Dùng để inject vào LLM context.
    """
    user_id: str
    total_relationships: int
    top_relationships: List[RelationshipEdge]
    recent_interactions: List[InteractionEvent]
    social_summary: str
    
    def to_llm_context(self) -> str:
        """Convert thành text cho LLM"""
        lines = ["\n[MẠNG LƯỚI QUAN HỆ CỦA USER]"]
        
        if self.top_relationships:
            lines.append("- Những người thân thiết nhất:")
            for rel in self.top_relationships[:5]:
                sentiment_emoji = {
                    SentimentType.POSITIVE: "😊",
                    SentimentType.NEUTRAL: "😐",
                    SentimentType.NEGATIVE: "😠",
                    SentimentType.MIXED: "🤔"
                }.get(rel.sentiment, "❓")
                
                lines.append(
                    f"  • {rel.target_display_name or rel.target_user_id}: "
                    f"{rel.relationship_type.value} {sentiment_emoji} "
                    f"(thân thiết: {rel.intimacy_score:.0%})"
                )
                
                if rel.relationship_facts:
                    for fact in rel.relationship_facts[:2]:
                        lines.append(f"    - {fact}")
        
        if self.social_summary:
            lines.append(f"\n- Tóm tắt: {self.social_summary}")
        
        return "\n".join(lines)
```

---

## 4. Event System Integration

### 4.1 Event Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    EVENT SYSTEM INTEGRATION                                  │
└─────────────────────────────────────────────────────────────────────────────┘

                    USER GỬI TIN NHẮN
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      ActiveMemoryService (T1)                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   1. add_message(user_id, role, content)                                   │
│      │                                                                      │
│      ├──▶ pipeline.evaluate_message(content, role)                         │
│      │    └──▶ Trả về: (score, category, extracted_content)                │
│      │                                                                      │
│      ├──▶ Kiểm tra @mentions trong content                                 │
│      │    │                                                                 │
│      │    └──▶ Nếu có mention:                                             │
│      │         ┌─────────────────────────────────────────┐                 │
│      │         │ EMIT: INTERACTION_OCCURRED              │                 │
│      │         │ data: {target_user_id, type: "mention"} │                 │
│      │         └─────────────────────────────────────────┘                 │
│      │                                                                      │
│      └──▶ Kiểm tra relationship keywords                                   │
│           │                                                                 │
│           └──▶ Nếu có khả năng chứa relationship:                          │
│                ┌─────────────────────────────────────────┐                 │
│                │ EMIT: RELATIONSHIP_DETECTED             │                 │
│                │ data: {content, context}                │                 │
│                └─────────────────────────────────────────┘                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                           │
                           │ Events emitted
                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      EventDispatcher                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                    SUBSCRIBERS REGISTRY                              │  │
│   │                                                                      │  │
│   │   INTERACTION_OCCURRED:                                              │  │
│   │     └──▶ RelationshipGraphManager.handle_interaction()              │  │
│   │                                                                      │  │
│   │   RELATIONSHIP_DETECTED:                                             │  │
│   │     └──▶ RelationshipGraphManager.handle_relationship_detected()    │  │
│   │                                                                      │  │
│   │   CRITICAL_INFO_DETECTED:                                            │  │
│   │     └──▶ CoreManager.handle_critical_info() (existing)              │  │
│   │                                                                      │  │
│   │   TOKEN_LIMIT_REACHED:                                               │  │
│   │     └──▶ MemoryManager._handle_memory_overflow() (existing)         │  │
│   │                                                                      │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                           │
                           │ Fire-and-forget async
                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                   RelationshipGraphManager                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   handle_interaction(event, user_id, data):                                │
│   │                                                                         │
│   ├──▶ Tạo InteractionEvent                                                │
│   ├──▶ Lưu vào storage                                                     │
│   └──▶ Cập nhật edge interaction_count                                     │
│                                                                             │
│   handle_relationship_detected(event, user_id, data):                      │
│   │                                                                         │
│   ├──▶ Gọi Extractor.extract_from_conversation()                           │
│   │    └──▶ LLM phân tích và trả về relationships                          │
│   │                                                                         │
│   └──▶ For each relationship:                                              │
│        └──▶ _update_relationship(user_id, rel_data)                        │
│             ├──▶ Nếu edge tồn tại: merge facts, update scores              │
│             └──▶ Nếu edge mới: tạo RelationshipEdge mới                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Code Changes Required

**Thêm events mới vào `event_dispatcher.py`:**

```python
# src/services/memories/activate_memory/events/event_dispatcher.py

class ActiveMemoryEvent(str, Enum):
    CRITICAL_INFO_DETECTED = "critical_info_detected"
    TOKEN_LIMIT_REACHED = "token_limit_reached"
    SESSION_TIMEOUT = "session_timeout"
    
    # === NEW EVENTS FOR RELATIONSHIP ===
    RELATIONSHIP_DETECTED = "relationship_detected"
    INTERACTION_OCCURRED = "interaction_occurred"
```

**Wire events trong `memory_manager.py`:**

```python
def _wire_events(self):
    # Existing wires...
    self.events.subscribe(
        ActiveMemoryEvent.CRITICAL_INFO_DETECTED, 
        self.t3.handle_critical_info
    )
    
    # === NEW WIRES FOR RELATIONSHIP GRAPH ===
    self.events.subscribe(
        ActiveMemoryEvent.RELATIONSHIP_DETECTED,
        self.relationship_graph.handle_relationship_detected
    )
    self.events.subscribe(
        ActiveMemoryEvent.INTERACTION_OCCURRED,
        self.relationship_graph.handle_interaction
    )
```

---

## 5. LLM Prompts cho Relationship Extraction

### 5.1 Extraction Prompt Template

```yaml
# src/services/relationship_graph/prompts.yaml

RELATIONSHIP_EXTRACTION_PROMPT: |
  role: "Chuyên gia Phân tích Mối quan hệ Xã hội"
  task: Phân tích đoạn hội thoại và trích xuất thông tin về mối quan hệ.
  
  context_rules:
    1. Tập trung vào statement về người thứ 3
    2. Chú ý từ khóa: bạn, crush, người yêu, anh/chị/em, đồng nghiệp
    3. Xác định sentiment: positive, negative, neutral
    4. Đánh giá intimacy level: 0.0 đến 1.0
  
  input_conversation: |
    {conversation}
  
  output_format: |
    Trả về JSON:
    ```json
    {
      "relationships": [
        {
          "target_name": "Tên người được nhắc",
          "relationship_type": "friend|family|romantic|colleague|acquaintance",
          "intimacy_score": 0.0-1.0,
          "sentiment": "positive|neutral|negative|mixed",
          "facts": ["Fact 1", "Fact 2"],
          "evidence": "Câu gốc"
        }
      ]
    }
    ```

EXAMPLES:
  - input: "Nam là bạn thân nhất của tao từ cấp 3"
    output:
      relationships:
        - target_name: "Nam"
          relationship_type: "friend"
          intimacy_score: 0.95
          sentiment: "positive"
          facts: ["Bạn thân từ cấp 3"]
          evidence: "Nam là bạn thân nhất của tao từ cấp 3"
  
  - input: "Crush tao tên Lan, học cùng lớp"
    output:
      relationships:
        - target_name: "Lan"
          relationship_type: "romantic"
          intimacy_score: 0.6
          sentiment: "positive"
          facts: ["Crush", "Học cùng lớp"]
          evidence: "Crush tao tên Lan"
```

### 5.2 Extraction Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    LLM EXTRACTION FLOW                                       │
└─────────────────────────────────────────────────────────────────────────────┘

    Input Conversation
           │
           ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │                                                                     │
    │   User: "Nam là bạn thân nhất của tao, tụi tao chơi với nhau       │
    │          10 năm rồi. Mà dạo này nó đang crush con Lan trong lớp"    │
    │                                                                     │
    └─────────────────────────────────────────────────────────────────────┘
           │
           ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │                      LLM PROCESSING                                  │
    │                                                                      │
    │   1. Parse entities: Nam, Lan                                       │
    │   2. Classify relationships:                                        │
    │      - Nam → friend (bạn thân nhất)                                 │
    │      - Lan → romantic (crush của Nam, không phải của user)          │
    │   3. Calculate scores:                                              │
    │      - Nam: intimacy=0.95, sentiment=positive                       │
    │      - Lan: intimacy=0.2, sentiment=neutral (không phải crush của user)│
    │   4. Extract facts:                                                 │
    │      - Nam: ["Bạn thân nhất", "Chơi 10 năm"]                        │
    │                                                                      │
    └─────────────────────────────────────────────────────────────────────┘
           │
           ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │                       OUTPUT JSON                                    │
    │                                                                      │
    │   {                                                                  │
    │     "relationships": [                                               │
    │       {                                                              │
    │         "target_name": "Nam",                                        │
    │         "relationship_type": "friend",                               │
    │         "intimacy_score": 0.95,                                      │
    │         "sentiment": "positive",                                     │
    │         "facts": ["Bạn thân nhất", "Chơi 10 năm"],                   │
    │         "evidence": "Nam là bạn thân nhất của tao"                   │
    │       },                                                             │
    │       {                                                              │
    │         "target_name": "Lan",                                        │
    │         "relationship_type": "acquaintance",                         │
    │         "intimacy_score": 0.2,                                       │
    │         "sentiment": "neutral",                                      │
    │         "facts": ["Crush của Nam", "Trong lớp"],                     │
    │         "evidence": "dạo này nó đang crush con Lan"                  │
    │       }                                                              │
    │     ]                                                                │
    │   }                                                                  │
    │                                                                      │
    └─────────────────────────────────────────────────────────────────────┘
```

---

## 6. API & Interface Design

### 6.1 RelationshipGraphManager API

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                RelationshipGraphManager PUBLIC API                           │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│   EVENT HANDLERS (Called by EventDispatcher)                               │
│   ─────────────────────────────────────────────                            │
│                                                                             │
│   async handle_relationship_detected(event_type, user_id, data)            │
│       • Xử lý event RELATIONSHIP_DETECTED                                  │
│       • Gọi LLM extraction                                                 │
│       • Update graph                                                       │
│                                                                             │
│   async handle_interaction(event_type, user_id, data)                      │
│       • Xử lý event INTERACTION_OCCURRED                                   │
│       • Log interaction event                                              │
│       • Update interaction counts                                          │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   PUBLIC API (Called by ChatCoordinator/MemoryManager)                     │
│   ─────────────────────────────────────────────────────────                │
│                                                                             │
│   async get_relationship_context(user_id, query) → (str, Snapshot)         │
│       • Lấy relationship context để inject vào LLM prompt                  │
│       • Trả về (text_context, snapshot)                                    │
│                                                                             │
│   async get_relationship(source_id, target_id) → RelationshipEdge | None   │
│       • Lấy relationship giữa 2 users                                      │
│                                                                             │
│   async get_all_relationships(user_id) → List[RelationshipEdge]            │
│       • Lấy tất cả relationships của user                                  │
│                                                                             │
│   async search_relationships(keyword) → List[RelationshipEdge]             │
│       • Tìm relationships theo tên hoặc fact                               │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   INTERNAL METHODS                                                          │
│   ─────────────────                                                         │
│                                                                             │
│   async _update_relationship(user_id, rel_data) → RelationshipEdge         │
│   async _increment_interaction_count(source_id, target_id)                 │
│   async _generate_social_summary(edges, query) → str                       │
│   _build_conversation_text(context, content) → str                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 6.2 Integration với ChatCoordinator

```python
# src/services/chat_coordinator.py (modified)

async def process_message(self, user_id: str, content: str) -> str:
    """
    Xử lý trọn vẹn 1 vòng đời của tin nhắn.
    """
    # 1. Ghi nhận tin nhắn của User
    await self.memory.add_message(user_id=user_id, role="user", content=content)
    
    # 2. Rút trích Ngữ cảnh từ Memory
    sys_prompt, context_msgs = await self.memory.get_context(
        user_id=user_id, current_query=content
    )
    
    # === NEW: Get relationship context ===
    rel_context, rel_snapshot = await self.relationship_graph.get_relationship_context(
        user_id, content
    )
    sys_prompt += rel_context
    # ===================================
    
    # 3. Gọi LLM sinh câu trả lời
    llm_response = await self.llm.generate_response(
        messages=context_msgs, system_prompt=sys_prompt
    )
    
    # 4. Ghi nhận câu trả lời của Bot
    await self.memory.add_message(
        user_id=user_id, role="assistant", content=bot_response
    )
    
    return bot_response
```

---

## 7. Implementation Roadmap

### Phase Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    IMPLEMENTATION PHASES                                     │
└─────────────────────────────────────────────────────────────────────────────┘

Phase 1: Core Models & Storage
├── models.py (Pydantic models)
├── storage/base_storage.py (Abstract)
└── storage/json_storage.py (Implementation)

Phase 2: LLM Extraction
├── prompts.yaml
├── extractor.py
└── Test với sample conversations

Phase 3: Event Integration
├── Update event_dispatcher.py
├── Wire events in memory_manager.py
└── Detection logic in activate_memory_service.py

Phase 4: Manager & API
├── manager.py (Facade)
├── Integration with chat_coordinator.py
└── Caching layer

Phase 5: Discord Commands
├── Re-enable !relationships
├── Add !relationship @user
└── Add !social_graph

Phase 6: Advanced Features
├── Bidirectional inference
├── Sentiment analysis
├── Relationship timeline
└── Vector search integration
```

### Detailed Checklist

**Phase 1: Core Models & Storage**
- [ ] Tạo `src/services/relationship_graph/` directory structure
- [ ] Implement `models.py` với Pydantic models
- [ ] Implement `storage/base_storage.py` abstract class
- [ ] Implement `storage/json_storage.py` (local JSON storage)
- [ ] Write unit tests cho models

**Phase 2: LLM Extraction**
- [ ] Tạo `prompts.yaml` với extraction prompts
- [ ] Implement `extractor.py`
- [ ] Test extraction với sample conversations
- [ ] Fine-tune prompts cho accuracy

**Phase 3: Event Integration**
- [ ] Thêm new events vào `event_dispatcher.py`
- [ ] Wire events trong `memory_manager.py`
- [ ] Implement detection logic trong `activate_memory_service.py`
- [ ] Test event flow end-to-end

**Phase 4: Manager & API**
- [ ] Implement `manager.py` facade
- [ ] Integrate với `chat_coordinator.py`
- [ ] Implement decay factor calculation
- [ ] Add caching layer

**Phase 5: Discord Commands**
- [ ] Re-enable `!relationships` command
- [ ] Add `!relationship @user` command
- [ ] Add `!social_graph` visualization command
- [ ] Add admin commands for relationship management

**Phase 6: Advanced Features**
- [ ] Implement bidirectional relationship inference
- [ ] Add sentiment analysis for interactions
- [ ] Implement relationship timeline/history
- [ ] Add vector search for relationship queries

---

## 📁 Proposed File Structure

```
src/services/relationship_graph/
├── __init__.py
├── manager.py              # RelationshipGraphManager (Facade)
├── extractor.py            # LLM-based extraction
├── models.py               # Pydantic models
├── prompts.yaml            # LLM prompts
├── storage/
│   ├── __init__.py
│   ├── base_storage.py     # Abstract interface
│   ├── json_storage.py     # Local JSON implementation
│   └── vector_storage.py   # Optional: Vector DB integration
└── utils/
    ├── __init__.py
    ├── mention_parser.py   # Parse @mentions from Discord
    └── sentiment.py        # Sentiment analysis helpers
```

---

## 🤔 Câu hỏi thảo luận

1. **Storage backend**: JSON local hay tích hợp với Vector DB hiện có (T2)?
2. **User ID resolution**: Làm sao map "tên trong chat" → "Discord user ID"?
3. **Privacy**: Có nên cho user xem/xóa relationship data của mình không?
4. **Performance**: Caching strategy cho relationship queries?
5. **Bidirectional inference**: Có nên tự động infer B→A từ A→B không?