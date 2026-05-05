# Multi-User Group Chat Architecture

## Overview: "Lễ tân" Bé Bảy & "Thủ thư" Evernight

Transform Discord bot from single-user conversations to full multi-user/group chat support.

### Problem Statement
1. Bot handles single-user conversations only
2. No cross-user profile retrieval (Quang asks about Hòa → bot doesn't know)
3. No group chat context - each message processed with sender's context only

### Solution
4-phase sequential implementation with security-first design.

---

## Phases

| Phase | Name | Duration | Dependencies |
|-------|------|----------|--------------|
| **1** | Alias Index | 4-6h | None |
| **2** | Group Chat Context | 6-8h | Phase 1 |
| **3** | Cross T3 Retrieval | 8-12h | Phase 2 |
| **4** | Nightly Maintenance | 4-6h | Can parallel with Phase 3 |

---

## Phase 1: Alias Index (Danh bạ Định danh)

**Goal:** Zero-latency user identity directory tracking aliases across servers.

**Storage:** `memories/INDEX.md`
```
Server_ID → User_ID → [Alias_History]
```

**Key Tasks:**
- Create `AliasStorage` class (Markdown parsing)
- Create `AliasManager` service (cache layer)
- Hook into `chat_gateway.py` (async background)
- Fire-and-forget pattern for zero-latency

**See:** `plan/phase-1-alias-index.md`

---

## Phase 2: Group Chat Context

**Goal:** Enable group chat context with channel-based sessions.

**Changes:**
- Storage key: `user_id` → `channel_id/thread_id`
- Message format: `[DisplayName]: content`
- Server directory injection into System Prompt

**Key Tasks:**
- Refactor T1 storage key
- Create `ChannelContext` class
- Inject server directory to System Prompt
- Handle both DM and Group uniformly

**See:** `plan/phase-2-group-chat.md`

---

## Phase 3: Cross T3 Retrieval

**Goal:** Cross-user profile retrieval with 4-layer consent mechanism.

**Tool:** `fetch_profile_tool.py`
- Security: Cross-server validation
- T3 sections: `## Public Info` / `## Private Info`

**4-Layer Consent:**
| Layer | Actor | Trigger |
|-------|-------|---------|
| 1 | User | Explicit command (`visibility=public/private`) |
| 2 | Chat Space | Group=Public, DM=Private |
| 3 | Evernight | Nightly review |
| 4 | Hardcoded | System prompt rules |

**See:** `plan/phase-3-cross-t3.md`

---

## Phase 4: Nightly Maintenance

**Goal:** Automated cleanup and restructuring.

**Tasks:**
- Alias cleanup (remove stale aliases)
- T3 section restructuring
- Stale data removal

**See:** `plan/phase-4-nightly.md`

---

## Constraints

| ID | Constraint |
|----|------------|
| CON-001 | Zero-latency user experience |
| CON-002 | No cross-server data leaks |
| CON-003 | DM behavior unchanged |
| CON-004 | Backward compatible |

---

## Acceptance Criteria

| ID | Criterion | Validation |
|----|-----------|------------|
| AC-001 | Users identified across servers/DMs | Integration test |
| AC-002 | Group messages with participant context | Unit + Integration |
| AC-003 | Cross-user profile with consent validation | Security test |
| AC-004 | No cross-server leaks | Penetration test |
| AC-005 | Zero-latency async processing | Performance test |