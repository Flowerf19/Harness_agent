---
status: active
created: 2026-05-29
---

# Memory System Test Plan — T1→T2→T3 End-to-End

## Objective

Verify T1 (active) → T2 (timeline) → T3 (profile) flow works correctly after memory rewrite. Test via browser to ensure agent reasoning + tool execution + recall work in production.

## Prerequisites

- Docker containers running: `march7`, `evernight`, `redis`
- Test user: Discord ID `726302130318868500`
- Browser DevTools open for network inspection

## Test Cases

### TC1: T3 Write — update_user_profile

**Goal:** Verify bot can write to T3 profile.

**Steps:**
1. Open Discord, mention `@March7`
2. Send: `"Mã kiểm thử memory 2026-05-29: phoenix-529"`
3. Bot should call `update_user_profile` with:
   - `user_id="726302130318868500"` (numeric, not username)
   - `section="rules"` or `"basic"`
   - `content="Mã kiểm thử memory 2026-05-29: phoenix-529"`

**Expected:**
- Bot confirms update
- File `/app/memories/726302130318868500.md` contains new line
- `docker exec march7-bot cat /app/memories/726302130318868500.md | grep phoenix-529` returns match

**Pass criteria:**
- ✅ Bot calls tool with correct numeric `user_id`
- ✅ File updated
- ✅ No error in logs

---

### TC2: T3 Read — get_profile

**Goal:** Verify bot can read from T3 profile.

**Steps:**
1. Send: `"Trong memory của tôi mã kiểm thử là gì?"`
2. Bot should:
   - Call `get_profile(user_id="726302130318868500")`
   - Parse result and extract `phoenix-529`
   - Reply with the code

**Expected:**
- Bot replies: `"Mã kiểm thử là phoenix-529"` (or similar)
- Tool call visible in logs with correct `user_id`

**Pass criteria:**
- ✅ Bot calls `get_profile` with numeric `user_id`
- ✅ Bot extracts and returns correct code
- ✅ No "Không tìm thấy" error

---

### TC3: T2 Search — search_memory

**Goal:** Verify bot can search T2 timeline memory.

**Steps:**
1. Have a conversation with 5+ messages about a topic (e.g., "Tôi thích anime One Piece")
2. Wait 30s for T1→T2 consolidation (or trigger manually via Evernight)
3. Send: `"Tôi đã nói gì về anime?"`
4. Bot should:
   - Call `search_memory(user_id="726302130318868500", mode="semantic", query="anime")`
   - Return T2 memories

**Expected:**
- Bot finds and returns memory about One Piece
- Tool call uses numeric `user_id`

**Pass criteria:**
- ✅ Bot calls `search_memory` with correct `user_id`
- ✅ Returns relevant T2 memory
- ✅ No "user_id không hợp lệ" error

---

### TC4: T1 Active Context

**Goal:** Verify T1 active memory works in conversation.

**Steps:**
1. Send: `"Tên tôi là Hoà"`
2. Send: `"Tên tôi là gì?"`
3. Bot should recall from T1 without calling tools

**Expected:**
- Bot replies: `"Hoà"` (from T1 context, no tool call)

**Pass criteria:**
- ✅ Bot recalls from T1 correctly
- ✅ No unnecessary tool calls

---

### TC5: Recall Priority — T3 > T2 > T1

**Goal:** Verify bot prioritizes T3 (profile) over T2 (timeline) for stable facts.

**Steps:**
1. Ensure T3 has: `"Nghề nghiệp: AI Engineer"` (from previous test or manual insert)
2. Send: `"Nghề của tôi là gì?"`
3. Bot should answer from T3 context (injected in system prompt), not call tools

**Expected:**
- Bot replies: `"AI Engineer"` without tool calls
- System prompt includes T3 profile context

**Pass criteria:**
- ✅ Bot answers from T3 context
- ✅ No tool call (T3 already in system prompt)

---

### TC6: User ID Validation

**Goal:** Verify tools reject invalid user_id.

**Steps:**
1. Manually trigger tool via Discord (if possible) or check logs
2. Observe bot behavior when it mistakenly passes `user_id="Flowerf"` (username)

**Expected:**
- Tool returns: `"Lỗi: user_id 'Flowerf' không hợp lệ. Phải là số ID Discord."`
- Bot should NOT retry with same invalid ID

**Pass criteria:**
- ✅ Tool validation works
- ✅ Bot receives clear error message

---

## Regression Checks

Compare with old memory system behavior:

| Feature | Old | New | Status |
|---|---|---|---|
| T3 update without explicit user_id | ✅ Bot/system auto-filled | ❌ Bot must pass numeric ID | **REGRESSION** → Fixed in this plan |
| T3 recall from system prompt | ✅ Worked | ❌ Failed (no user_id in prompt) | **REGRESSION** → Fixed in manager.py |
| T2 search with username | ❌ Never worked | ❌ Still doesn't work | No regression |
| T1 context recall | ✅ Worked | ✅ Should work | No regression |

---

## Execution Checklist

- [ ] TC1: T3 Write
- [ ] TC2: T3 Read
- [ ] TC3: T2 Search
- [ ] TC4: T1 Active
- [ ] TC5: Recall Priority
- [ ] TC6: User ID Validation
- [ ] Regression: Compare old vs new behavior
- [ ] Logs: No errors in `docker logs march7-bot`
- [ ] Metrics: Check Redis keys `t2:mem:*`, `t2:topic:*`, `active:*`

---

## Success Criteria

**PASS if:**
- All 6 test cases pass
- No "user_id không hợp lệ" errors
- Bot consistently uses numeric Discord ID from system prompt
- T3 recall works without tool calls
- T2 search returns relevant memories

**FAIL if:**
- Bot passes username instead of numeric ID
- T3 recall returns "Không tìm thấy" despite data existing
- Tool validation doesn't catch invalid user_id
- Regression: old features broken

---

## Notes

- Test user ID: `726302130318868500`
- Test codes: `phoenix-529` (today), `lotus-528` (yesterday)
- Browser DevTools: Monitor network tab for A2A calls
- Redis inspection: `docker exec march7-redis redis-cli`
