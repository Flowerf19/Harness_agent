---
status: active
created: 2026-05-31
test_user_id: 726302130318868500
---

# End-to-End Memory System Test Plan

## Pre-requisites Check

### 1. Environment Setup
- [ ] Docker containers running: `march7`, `evernight`, `march7-redis`
- [ ] LLM provider có credits (check logs không có "insufficient credits")
- [ ] Redis indexes exist: `idx:t2:mem`, `idx:t2:topic`
- [ ] Test user profile exists: `/app/memories/726302130318868500.md`

**Commands:**
```bash
# Check containers
docker ps --filter "name=march7"

# Check LLM provider
docker exec march7 env | grep LLM_PROVIDER

# Check Redis indexes
docker exec march7-redis redis-cli FT._LIST

# Check test user profile
docker exec march7 cat /app/memories/726302130318868500.md
```

---

## Test Scenarios

### Scenario 1: T3 Profile Write & Read (Basic Flow)

**Objective:** Verify bot can write to and read from T3 profile.

**Test Steps:**

1. **Setup - Clear old test data**
   ```bash
   # Backup current profile
   docker exec march7 cp /app/memories/726302130318868500.md /app/memories/726302130318868500.md.backup-$(date +%s)
   ```

2. **TC1.1: Write to T3 via conversation**
   - Open Discord Web (https://discord.com/channels/@me)
   - Login (user will help)
   - Find March7 bot DM or mention in channel
   - Send: `"Mã kiểm thử memory 2026-05-31: dragon-531"`
   - **Expected:** Bot confirms and updates profile

3. **TC1.2: Verify T3 file updated**
   ```bash
   docker exec march7 cat /app/memories/726302130318868500.md | grep "dragon-531"
   ```
   - **Expected:** File contains the test code

4. **TC1.3: Read from T3**
   - Send: `"Trong memory của tôi mã kiểm thử là gì?"`
   - **Expected:** Bot replies with `"dragon-531"`

5. **TC1.4: Check logs for tool calls**
   ```bash
   docker logs march7 --tail 50 | grep -E "update_user_profile|get_profile"
   ```
   - **Expected:** See tool calls with correct `user_id=726302130318868500`

**Pass Criteria:**
- ✅ Bot calls `update_user_profile` with numeric user_id
- ✅ File updated with new content
- ✅ Bot can recall from T3
- ✅ No "user_id không hợp lệ" errors

---

### Scenario 2: T1 Active Memory (Short-term Recall)

**Objective:** Verify T1 active memory works within conversation.

**Test Steps:**

1. **TC2.1: Store in T1**
   - Send: `"Tên tôi là Hoà"`
   - Wait 2 seconds
   - Send: `"Tên tôi là gì?"`
   - **Expected:** Bot replies `"Hoà"` without calling tools

2. **TC2.2: Verify no tool calls**
   ```bash
   docker logs march7 --tail 30 | grep -E "search_memory|get_profile" | tail -5
   ```
   - **Expected:** No recent tool calls (bot used T1 context)

3. **TC2.3: Check T1 Redis keys**
   ```bash
   docker exec march7-redis redis-cli KEYS "active:user:726302130318868500:*" | head -5
   ```
   - **Expected:** See active memory keys

**Pass Criteria:**
- ✅ Bot recalls from T1 correctly
- ✅ No unnecessary tool calls
- ✅ T1 keys exist in Redis

---

### Scenario 3: T2 Timeline Memory (Long-term Search)

**Objective:** Verify T2 consolidation and search work.

**Test Steps:**

1. **TC3.1: Create conversation for consolidation**
   - Have a 5-message conversation about a topic:
     - `"Tôi thích anime One Piece"`
     - `"Luffy là nhân vật yêu thích của tôi"`
     - `"Tôi đã xem đến arc Wano"`
     - `"Tôi thích phong cách vẽ của Oda"`
     - `"One Piece là anime hay nhất"`

2. **TC3.2: Wait for T1→T2 consolidation**
   - Wait 60 seconds (T1 token threshold + consolidation)
   - Check logs:
   ```bash
   docker logs march7 --tail 50 | grep "T2:consolidator"
   ```
   - **Expected:** See consolidation triggered

3. **TC3.3: Verify T2 memories created**
   ```bash
   docker exec march7-redis redis-cli KEYS "t2:mem:726302130318868500:*" | wc -l
   ```
   - **Expected:** At least 1 memory created

4. **TC3.4: Search T2 memory**
   - Send (in new conversation or after 5 min): `"Tôi đã nói gì về anime?"`
   - **Expected:** Bot recalls One Piece information

5. **TC3.5: Check search tool call**
   ```bash
   docker logs march7 --tail 50 | grep "search_memory"
   ```
   - **Expected:** See `search_memory` tool call with correct user_id

6. **TC3.6: Inspect T2 memory structure**
   ```bash
   # Get first memory key
   KEY=$(docker exec march7-redis redis-cli KEYS "t2:mem:726302130318868500:*" | head -1)
   docker exec march7-redis redis-cli JSON.GET "$KEY"
   ```
   - **Expected:** JSON with `embedding` (768 floats), `catalogs`, `topic_ids`

**Pass Criteria:**
- ✅ T1→T2 consolidation triggered
- ✅ T2 memories created with embeddings
- ✅ Bot can search and recall from T2
- ✅ `search_memory` tool uses correct user_id

---

### Scenario 4: T3 Promotion (T2→T3 Auto-promotion)

**Objective:** Verify high-importance T2 memories auto-promote to T3.

**Test Steps:**

1. **TC4.1: Provide high-importance info**
   - Send: `"Nghề nghiệp của tôi là AI Engineer tại Google"`
   - Wait 60s for consolidation

2. **TC4.2: Check T3 file for promotion**
   ```bash
   docker exec march7 cat /app/memories/726302130318868500.md | grep -i "AI Engineer"
   ```
   - **Expected:** Work section contains the info

3. **TC4.3: Verify T3 recall without tool**
   - Send (new conversation): `"Nghề của tôi là gì?"`
   - **Expected:** Bot answers from T3 context (no tool call)

**Pass Criteria:**
- ✅ High-importance info auto-promoted to T3
- ✅ Bot recalls from T3 without tool calls

---

### Scenario 5: Memory Priority (T3 > T2 > T1)

**Objective:** Verify bot prioritizes T3 over T2 over T1.

**Test Steps:**

1. **TC5.1: Ensure T3 has stable fact**
   - Verify T3 has: `"Nghề nghiệp: AI Engineer"` (from TC4)

2. **TC5.2: Test recall priority**
   - Send: `"Công việc của tôi là gì?"`
   - **Expected:** Bot answers from T3 context immediately

3. **TC5.3: Check system prompt injection**
   ```bash
   docker logs march7 --tail 100 | grep -A5 "system_prompt" | head -20
   ```
   - **Expected:** System prompt includes T3 context

**Pass Criteria:**
- ✅ Bot uses T3 context first
- ✅ No tool calls for T3-available info

---

### Scenario 6: User ID Validation

**Objective:** Verify tools reject invalid user_id.

**Test Steps:**

1. **TC6.1: Check tool validation**
   - This is tested implicitly in all above scenarios
   - All tool calls should use numeric `726302130318868500`

2. **TC6.2: Review logs for validation errors**
   ```bash
   docker logs march7 --tail 200 | grep -i "user_id.*không hợp lệ"
   ```
   - **Expected:** No validation errors (or only old ones)

**Pass Criteria:**
- ✅ All tool calls use numeric user_id
- ✅ No "user_id không hợp lệ" errors

---

## Regression Checks

### Check 1: T2 Vector Search (Not Fake)
```bash
docker exec march7-redis redis-cli FT.INFO idx:t2:mem | grep -A10 "VECTOR"
```
**Expected:** See `VECTOR HNSW` with `dim 768`

### Check 2: No Data Loss
```bash
# Check T1 cleanup doesn't delete before T2 write
docker logs march7 --tail 200 | grep -E "T1: trim|T2:consolidator"
```
**Expected:** T2 consolidation completes before T1 trim

### Check 3: Bot Replies in T2
```bash
# Check bot messages are captured
docker exec march7-redis redis-cli JSON.GET "$(docker exec march7-redis redis-cli KEYS 't2:mem:*' | head -1)" | grep -o '"speaker":"[^"]*"'
```
**Expected:** See `"speaker":"bot"` or `"speaker":"joint"` entries

---

## Critical Issues to Watch

### Issue 1: LLM Provider Credits
**Current Status:** ❌ FAILING - "insufficient credits" errors in logs

**Fix:**
```bash
# Switch to Gemini or check OpenAI credits
docker exec march7 env | grep -E "LLM_PROVIDER|GEMINI_API_KEY|OPENAI_API_KEY"
```

**Action:** Update `.env` or restart with valid provider

### Issue 2: Embedding Service
```bash
# Check embedding provider
docker exec march7 env | grep EMBEDDING_PROVIDER
```
**Expected:** `EMBEDDING_PROVIDER=gemini` or `openai_compat` with valid key

---

## Browser Testing Workflow

### Setup
1. Open Discord Web: https://discord.com/channels/@me
2. User logs in
3. Find March7 bot (DM or channel)

### Test Execution
1. Run Scenario 1 (T3 Write/Read) - 5 min
2. Run Scenario 2 (T1 Active) - 3 min
3. Run Scenario 3 (T2 Search) - 10 min (includes wait time)
4. Run Scenario 4 (T3 Promotion) - 5 min
5. Run Scenario 5 (Priority) - 3 min
6. Run Scenario 6 (Validation) - 2 min

**Total Time:** ~30 minutes

### Monitoring Commands (Run in parallel terminal)
```bash
# Watch logs live
docker logs march7 -f | grep -E "T1:|T2:|T3:|ERROR|WARNING"

# Watch Redis keys
watch -n 5 'docker exec march7-redis redis-cli KEYS "t2:mem:726302130318868500:*" | wc -l'

# Watch T3 file
watch -n 5 'docker exec march7 cat /app/memories/726302130318868500.md | tail -20'
```

---

## Success Criteria Summary

**PASS if:**
- ✅ All 6 scenarios pass
- ✅ No "insufficient credits" errors
- ✅ No "user_id không hợp lệ" errors
- ✅ T2 has VECTOR HNSW index
- ✅ Bot uses numeric Discord ID consistently
- ✅ T3 recall works without tool calls
- ✅ T2 search returns relevant memories

**FAIL if:**
- ❌ LLM provider errors block consolidation
- ❌ Bot passes username instead of numeric ID
- ❌ T3 recall returns "Không tìm thấy" despite data existing
- ❌ T2 consolidation creates 0 candidates (data loss)
- ❌ Vector search not working (fake Python loop)

---

## Post-Test Cleanup

```bash
# Restore backup if needed
docker exec march7 cp /app/memories/726302130318868500.md.backup-XXXXX /app/memories/726302130318868500.md

# Clear test T2 memories (optional)
docker exec march7-redis redis-cli KEYS "t2:mem:726302130318868500:*" | xargs docker exec march7-redis redis-cli DEL
```
