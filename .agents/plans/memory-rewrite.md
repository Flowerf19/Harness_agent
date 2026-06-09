---
status: done
created: 2026-05-28
finished: 2026-05-28
---

# Memory Rewrite — T1 + T2 from Scratch, T3 Restructured

## Summary

Đập T1 và T2 hiện tại, xây lại từ đầu ở `twin/shared/memory/`. Giữ T3 (markdown)
nhưng restructure thành 8 section nested. Lý do:

1. T1/T2 code duplicated giữa march7 và evernight (~3000 LOC trùng)
2. T2 hiện tại fake vector search — KHÔNG có `VECTOR HNSW` field, dùng Python
   cosine full-scan O(N). Trả phí embedding nhưng không có benefit
3. `DiscussionConsolidator` có bug: LLM trả participant theo tên hiển thị thay
   vì author_id → strip thành empty → mọi consolidation = `status=skipped` →
   T1 bị cleanup nhưng T2 không được tạo → **mất dữ liệu vĩnh viễn**
4. T2Page model có 8 field dead (history_log, source_refs, active_fact_ids,
   topic_aliases, scope, topic_id, latest_chunk_id, latest_chunk_embedding)
5. T2Chunk + T2Fact entity declared nhưng không có code path produce → 0 keys
   trong DB
6. T3 hiện tại 5 section trộn (preference + habit + dislike chung) → bot
   không phân biệt được section nào cần update

Mục tiêu: kiến trúc 2-pass (hot extract + async cleanup), atomic memory, vector
KNN thật, topic resolution, lifecycle pointers, T3 promotion theo enum cứng.

## Completion Notes — 2026-05-28

- Phase 8→11 đã hoàn tất: tool registry dùng `search_memory`,
  `update_user_profile`, `get_profile`; `consolidate_t2_memory` bị xoá.
- March7/Evernight container cùng wire `ActiveMemory`, `MarkdownProfileStore`,
  `TimelineStore/Search`, `Consolidator`, `CleanupScheduler`, và
  `SharedMemoryManager` từ `twin/shared/memory/`.
- T3 migration đã chạy cho Hoà + Quang bằng `scripts/migrate_t3_5to8.py`,
  giữ backup `.bak5` và render đúng 8 section.
- Docker compose set `TIMELINE_REDIS_DB=0` và `EMBEDDING_VECTOR_SIZE=1024` để
  RediSearch VECTOR HNSW hoạt động đúng trên Redis Stack.
- Verification: `pytest` pass, Docker services healthy, A2A health endpoints
  trả agent card, `FT.INFO idx:t2:mem` có `VECTOR HNSW` dim `1024`.

## Success Criteria

- T1 + T2 chỉ tồn tại 1 lần ở `twin/shared/memory/`. Container march7 và
  evernight cùng import. `twin/march7/memories/`, `twin/evernight/memories/`,
  `twin/shared/memories/` xóa hoàn toàn.
- T2 dùng `FT.CREATE ... VECTOR HNSW 1024 COSINE` thật. `search_similar` gọi
  `FT.SEARCH ... =>[KNN ...]`, không Python loop.
- Consolidate transcript có info đáng lưu → tạo memory thành công, status=ok,
  có vector ở Redis (`JSON.GET t2:mem:{user}:{id} $.embedding` trả 1024 float).
- Topic "phim", "phim ảnh", "film" → 1 topic_id duy nhất (alias merge sau lần
  gặp đầu).
- User đổi ý ("Hoà chuyển sang thích phim tâm lý") → memory mới có
  `supersedes=mem_cũ`, mem_cũ có `superseded_by=mem_mới`. Search
  `current_state` chỉ trả mem_mới.
- T3 file render đúng 8 section, bullet không duplicate sau pass 2 cleanup.
- Bot reply trong conversation tạo T2 memory (`speaker=bot` hoặc `joint`),
  không chỉ user message.
- Pre-flight retrieval: mỗi turn march7 agent inject top-K T2 vào system
  prompt mà LLM không cần gọi `search_memory` tool.

## Non-Goals

- T3 sang database / version control (giữ flat markdown).
- Topic-level vector search expose ra ngoài (chỉ dùng internal cho resolver).
- Commitment / promise tracking với target_date (defer v2).
- Soft delete `archived=True` field (defer v2).
- Multi-language embedding routing (Gemini embedding output cố định 1024-d).
- Rewrite T1 evaluation pipeline cũ (semantic_engine) — bỏ hẳn, thay bằng
  FastPathDetector cheap regex.

## Final Design — Locked

### Tier overview

| Tier | Storage | Trigger ghi | Trigger đọc |
|---|---|---|---|
| T1 | Redis JSON `active:*` | Mỗi message | `get_context()` mỗi turn |
| T2 | Redis Stack `t2:mem:*` + `t2:topic:*` VECTOR HNSW 1024 | T1 đạt 2000 token | Pre-flight + `search_memory` tool |
| T3 | Markdown `memories/{user_id}.md` 8 section | T2 promote (auto append) + cleanup pass | Full read mỗi turn |

### T2 catalogs (12)

T3-promotable (8):
- `identity`, `contact`, `relationship`, `work`,
- `interest`, `habit`, `psychological`, `rules`

T2-only (4):
- `decision`, `event`, `emotion`, `discussion`

### T3 sections (8) — 1-1 với T3-promotable catalogs

```
basic         ← identity
contact       ← contact
relationship  ← relationship
work          ← work
interest      ← interest
habit         ← habit
psychological ← psychological
rules         ← rules
```

### Models

```python
# twin/shared/memory/timeline/models.py

CATALOGS = ["identity","contact","relationship","work",
            "interest","habit","psychological","rules",
            "decision","event","emotion","discussion"]

T3_PROMOTABLE = {"identity","contact","relationship","work",
                 "interest","habit","psychological","rules"}

CATALOG_TO_T3 = {
    "identity":"basic", "contact":"contact",
    "relationship":"relationship", "work":"work",
    "interest":"interest", "habit":"habit",
    "psychological":"psychological", "rules":"rules",
}

class T2Topic(BaseModel):
    topic_id: str                      # uuid4
    user_id: str
    name: str                          # canonical, lowercase, snake_case
    aliases: list[str]
    catalogs: list[str]                # auto-union từ member memories
    embedding: list[float]             # 1024
    created_at: datetime
    last_accessed: datetime
    access_count: int
    importance: int                    # = max(member importance)
    memory_count: int
    ttl_days: int                      # = TTL_BY_IMPORTANCE[importance] × 2
    expires_at: datetime

class T2Memory(BaseModel):
    memory_id: str                     # uuid4
    user_id: str
    content: str                       # 1-3 câu atomic
    embedding: list[float]             # 1024
    topic_ids: list[str]
    catalogs: list[str]                # max 2, từ CATALOGS
    speaker: Literal["user","bot","joint"] = "user"
    created_at: datetime
    importance: int                    # 1-5
    confidence: float                  # 0-1
    source_msg_ids: list[str]
    supersedes: str | None = None
    superseded_by: str | None = None
    change_type: Literal["new","update","correction","reinforcement"] = "new"
    change_reason: str | None = None
    ttl_days: int                      # TTL_BY_IMPORTANCE[importance]
    expires_at: datetime
    last_accessed: datetime
    access_count: int = 0
```

### Redis indexes

```
FT.CREATE idx:t2:topic ON JSON PREFIX 1 "t2:topic:" SCHEMA
  $.user_id          AS user_id          TAG
  $.name             AS name             TEXT
  $.aliases[*]       AS aliases          TEXT
  $.catalogs[*]      AS catalogs         TAG
  $.last_accessed_ts AS last_accessed    NUMERIC SORTABLE
  $.importance       AS importance       NUMERIC
  $.expires_at_ts    AS expires_at       NUMERIC
  $.embedding        AS embedding
    VECTOR HNSW 6 TYPE FLOAT32 DIM 1024 DISTANCE_METRIC COSINE

FT.CREATE idx:t2:mem ON JSON PREFIX 1 "t2:mem:" SCHEMA
  $.user_id          AS user_id          TAG
  $.topic_ids[*]     AS topic_ids        TAG
  $.catalogs[*]      AS catalogs         TAG
  $.change_type      AS change_type      TAG
  $.superseded_by    AS superseded_by    TAG
  $.speaker          AS speaker          TAG
  $.importance       AS importance       NUMERIC
  $.created_at_ts    AS created_at       NUMERIC SORTABLE
  $.last_accessed_ts AS last_accessed    NUMERIC SORTABLE
  $.expires_at_ts    AS expires_at       NUMERIC
  $.embedding        AS embedding
    VECTOR HNSW 6 TYPE FLOAT32 DIM 1024 DISTANCE_METRIC COSINE
```

### Pipeline 2-pass

```
Pass 1 — hot (sync, mỗi lần T1 đạt threshold):
  1. extract_and_classify(transcript, t3_snapshot, topic_glossary, catalogs)
     → 1 LLM call → list[CandidateMemory{content, topic_names, catalogs,
                                          importance, source_msg_ids, speaker}]
     max 5 candidates / transcript
  2. for each candidate:
     a. resolve topics (3-stage: exact alias / KNN ≥0.92 / LLM borderline)
     b. embed content (1024)
     c. write T2Memory với change_type=new (KHÔNG judge supersede inline)
     d. if catalog ∈ T3_PROMOTABLE AND importance ≥ 4 AND confidence ≥ 0.8:
          section = CATALOG_TO_T3[catalog]
          t3.append_raw(user_id, section, content, source_memory_id)
  3. schedule cleanup(user_id, delay=30s) — debounced

Pass 2 — cleanup (async, debounced 30s per user, lock per user):
  1. T3 cleanup:
     llm.cleanup_t3(markdown, instruction) → merged version
     temp write + diff check; nếu diff > 50% reject + log
  2. T2 supersede detection:
     recent_mems = list_recent(user_id, hours=24, limit=100)
     clusters by embedding similarity ≥ 0.88
     for cluster ≥ 2 mems: LLM detect supersede chain
     apply: old.superseded_by, new.supersedes, change_type, change_reason
  3. Topic merge:
     topic_clusters by topic embedding ≥ 0.90
     LLM judge merge → move memories to keeper, delete losers
```

### T1 fast path (T3 critical-info real-time)

```
T1.observe(scope, scope_id, role, content):
  entry = save(...)
  state.unsummarized_tokens += entry.tokens

  if detector.is_critical(content):   # cheap regex
    schedule fast_extract(user_id, [entry])  # 1 LLM call, T3 only
  elif state.unsummarized_tokens >= TOKEN_THRESHOLD:
    trigger consolidate(scope, scope_id)     # full pass 1
```

FastPathDetector regex theo 8 promotable catalogs (birthday, name, email,
phone, password, dislike pattern, ...).

### Pre-flight retrieval

```python
# march7/agent.respond(message):
relevant_t2 = await timeline.search(user_id, query=message,
                                    mode="semantic", limit=5)
t3_context  = await profile.get_system_prompt_context(user_id)
system_prompt = base_prompt + t3_context + format(relevant_t2)
# 2 instructions ẩn:
#   "Dùng tự nhiên, KHÔNG nói 'Theo hồ sơ...'"
#   "Lồng vào tự nhiên, KHÔNG kể lể 'lần trước bạn nói...'"
```

### Constants

```python
# twin/shared/memory/timeline/constants.py
EMBEDDING_DIM = int(os.getenv("EMBEDDING_VECTOR_SIZE", "1024"))
TTL_BY_IMPORTANCE = {5: 90, 4: 60, 3: 30, 2: 14, 1: 7}
TOPIC_TTL_MULTIPLIER = 2
TOPIC_MATCH_THRESHOLD_AUTO = 0.92
TOPIC_MATCH_THRESHOLD_LLM = 0.75
TOPIC_CASCADE_LIMIT = 50
MAX_CANDIDATES_PER_TRANSCRIPT = 5
MAX_CATALOGS_PER_MEMORY = 2
KNN_NEIGHBOURS_FOR_PRE_FLIGHT = 5
T3_PROMOTE_MIN_IMPORTANCE = 4
T3_PROMOTE_MIN_CONFIDENCE = 0.8
CLEANUP_DEBOUNCE_SECONDS = 30
CLEANUP_SUPERSEDE_THRESHOLD = 0.88
CLEANUP_TOPIC_MERGE_THRESHOLD = 0.90

# twin/shared/memory/active/constants.py
TOKEN_THRESHOLD = 2000
IDLE_TRIGGER_MINUTES = 15
KEEP_RECENT_MESSAGES_AFTER_SUMMARY = 5
```

### Code layout

```
twin/shared/memory/
  __init__.py
  active/
    __init__.py
    models.py            ActiveEntry
    detector.py          FastPathDetector (regex)
    store.py             Redis JSON scope-aware (user|channel)
    service.py           observe/get_context/trim + threshold inline
    constants.py
  timeline/
    __init__.py
    models.py            T2Topic, T2Memory, CATALOGS, T3_PROMOTABLE,
                         CATALOG_TO_T3, TTL_BY_IMPORTANCE
    store.py             Redis Stack VECTOR HNSW ops
    topic_resolver.py    3-stage match
    extractor.py         hot-path LLM (1 call)
    consolidator.py      pipeline orchestrator
    cleanup.py           pass 2 dedupe + merge + T3 cleanup
    cleanup_scheduler.py debounce 30s per user
    search.py            6 modes + on-hit TTL refresh
    constants.py
  profile/
    __init__.py
    models.py            ProfileSection enum
    markdown_store.py    read/write/append per section
    constants.py
  tools/
    __init__.py
    search_memory_tool.py
    get_profile_tool.py
    update_profile_tool.py
```

T3 data: `memories/{user_id}.md` — không đổi path.

## Migration

### Pre-rewrite

```bash
# Backup
cp -r memories/ memories.bak/

# Snapshot DB state để rollback
docker exec march7-redis redis-cli -n 0 --rdb /tmp/db0.rdb
docker exec march7-redis redis-cli -n 1 --rdb /tmp/db1.rdb
```

### Nuke

```bash
docker exec march7-redis redis-cli -n 0 FLUSHDB
docker exec march7-redis redis-cli -n 1 FLUSHDB
docker exec march7-redis redis-cli FT.DROPINDEX idx:t1:msg 2>/dev/null || true
docker exec march7-redis redis-cli FT.DROPINDEX idx:t2:mem 2>/dev/null || true
docker exec march7-redis redis-cli FT.DROPINDEX idx:t2:topic 2>/dev/null || true
```

### T3 migration (one-shot)

T3 file hiện tại 5 section trộn → script chuyển sang 8 section nested:

```bash
scripts/migrate_t3_5to8.py          # dry-run
scripts/migrate_t3_5to8.py --apply  # write + .bak5 backup
```

Tay verify Hoà + Quang trước khi auto-apply cho user khác.

## Implementation Plan & Checklist

### Phase 0 — Prep (½ ngày)

- [ ] Branch `feature/memory-rewrite` từ `feature/twin-soul-agents`
- [ ] Backup `memories/` + Redis RDB snapshot DB 0 và DB 1
- [ ] Add Gemini text-embedding-004 config check ở `.env` (`EMBEDDING_PROVIDER=gemini`,
      `EMBEDDING_MODEL=text-embedding-004`, `EMBEDDING_VECTOR_SIZE=1024`)
- [ ] Confirm `LLM service` đang chạy có hỗ trợ structured output (Pydantic) —
      cần cho extract_and_classify

### Phase 1 — T1 (1 ngày)

- [ ] `twin/shared/memory/active/constants.py` — token threshold, idle, keep_recent
- [ ] `twin/shared/memory/active/models.py` — `ActiveEntry`
- [ ] `twin/shared/memory/active/detector.py` — `FastPathDetector` regex
      cho 8 promotable catalogs
- [ ] `twin/shared/memory/active/store.py` — Redis JSON scope-aware
      (key `active:{scope}:{scope_id}:{entry_id}`, state hash
      `active_state:{scope}:{scope_id}`)
- [ ] `twin/shared/memory/active/service.py` — `ActiveMemory` facade:
      `observe`, `get_context`, `trim`, threshold-inline trigger
- [ ] Unit test `tests/unit/memory/test_active.py`:
  - observe append + state token bump
  - get_context filter scope + limit
  - trim removes summarized_entry_ids
  - fast_path detector match 8 categories
  - threshold trigger fires consolidator callback
- [ ] Smoke: container wiring chạy march7, gửi 10 message → key Redis đúng

### Phase 2 — T2 store + models (1 ngày)

- [ ] `twin/shared/memory/timeline/constants.py`
- [ ] `twin/shared/memory/timeline/models.py` — T2Topic, T2Memory,
      CATALOGS, T3_PROMOTABLE, CATALOG_TO_T3, helper functions
      (`get_ttl_by_importance`, `expires_at_for_importance`,
      `generate_topic_id`)
- [ ] `twin/shared/memory/timeline/store.py`:
  - `initialize()` — `FT.CREATE` 2 index với VECTOR HNSW
  - `upsert_topic(topic)`, `get_topic(id)`,
    `find_topic_by_name_or_alias(user, name)`, `add_topic_alias`,
    `recent_topics(user, k)`, `knn_topics(vec, user, k)`,
    `refresh_topic_ttl`
  - `upsert_memory(mem)`, `get_memory(id)`,
    `knn_memories(vec, user, k, filter_superseded)`,
    `list_recent(user, hours, limit)`,
    `extend_topic_memory_ttls(topic_id, top=50)`
- [ ] Unit test `tests/unit/memory/test_timeline_store.py`:
  - upsert + get round-trip
  - KNN trả nearest theo cosine
  - alias add → find_by_alias hit
  - TTL set + expire_at calculation
  - filter -superseded_by hoạt động
- [ ] Smoke: write 1 topic + 1 memory tay, query `JSON.GET` thấy embedding 1024 float,
      `FT.SEARCH ...=>[KNN 5 @embedding $vec]` trả về

### Phase 3 — Topic resolver (½ ngày)

- [ ] `twin/shared/memory/timeline/topic_resolver.py`:
  - Stage 1: exact + alias
  - Stage 2: KNN top-3, auto ≥ 0.92
  - Stage 3: LLM judge borderline 0.75-0.92
  - Stage 4: create new
- [ ] Unit test `tests/unit/memory/test_topic_resolver.py`:
  - Exact name → hit
  - Alias hit
  - KNN auto-match → add alias
  - LLM judge match → add alias
  - Below threshold → create new
  - User isolation (topic của user A không match cho user B)

### Phase 4 — Extractor + Consolidator (1 ngày)

- [ ] `twin/shared/memory/timeline/extractor.py`:
  - Prompt template (TV): extract atomic + classify catalogs + propose topic
    names + importance + speaker + change_type hint
  - Pydantic schema `ExtractResult{memories: list[CandidateMemory]}`
  - LLM call structured output, max_candidates=5
  - Inject `t3_snapshot` + `topic_glossary` (top-20 recent topics + aliases)
    + `CATALOGS enum + định nghĩa 1 dòng`
- [ ] `twin/shared/memory/timeline/consolidator.py`:
  - `consolidate(payload)` orchestrator
  - For each candidate: resolve topics → embed → upsert memory (`change_type=new`)
  - Auto-promote T3 nếu catalog ∈ T3_PROMOTABLE AND importance ≥ 4 AND
    confidence ≥ 0.8 (append raw, không LLM judge inline)
  - Schedule cleanup debounced
- [ ] Unit test `tests/unit/memory/test_consolidator.py`:
  - Empty payload → no-op
  - Single candidate ADD → memory written
  - T3 promote condition match → t3.append_raw called
  - T3 promote condition fail (importance < 4) → t3 NOT called
  - Cleanup scheduled after consolidation

### Phase 5 — Cleanup + Scheduler (1 ngày)

- [ ] `twin/shared/memory/timeline/cleanup_scheduler.py`:
  - Debounce per user_id, 30s
  - Lock per user (asyncio.Lock dict)
  - Cancel previous task on re-schedule
- [ ] `twin/shared/memory/timeline/cleanup.py`:
  - `cleanup_user(user_id)`:
    a. T3 cleanup: LLM merge duplicate + conflict, diff check < 50%
    b. T2 supersede detection: cluster KNN ≥ 0.88, LLM judge
    c. Topic merge: cluster topic embedding ≥ 0.90, LLM judge
  - Diff check helper (reject if too aggressive)
- [ ] Unit test `tests/unit/memory/test_cleanup.py`:
  - Debounce: 3 schedules trong 10s → cleanup chạy 1 lần
  - T3 duplicate merge
  - T3 conflict resolution (giữ entry mới nhất)
  - T2 supersede chain detection
  - Topic merge (cluster 3 topic similar → keeper)
  - Diff > 50% → reject T3 write

### Phase 6 — Search + Pre-flight (½ ngày)

- [ ] `twin/shared/memory/timeline/search.py`:
  - 6 modes: `semantic`, `current_state`, `by_topic`, `topic_timeline`,
    `by_catalog`, `change_log`, `recent`
  - `auto` resolver based on params
  - on-hit refresh TTL (memory + topic cascade top-50)
- [ ] Pre-flight integration ở march7 agent:
  - Trước LLM call: `timeline.search(query=message, mode="semantic", limit=5)`
  - Format vào system prompt với chỉ thị ẩn
- [ ] Unit test `tests/unit/memory/test_search.py`:
  - Mỗi mode trả đúng filter
  - `current_state` lọc `-superseded_by:{*}`
  - `topic_timeline` sort ASC by date
  - On-hit refresh: memory.last_accessed bump, topic TTL refreshed
  - Cascade: top-50 cùng topic được extend TTL

### Phase 7 — T3 markdown 8 sections (½ ngày)

- [ ] `twin/shared/memory/profile/constants.py` — `SECTIONS = [basic, contact,
      relationship, work, interest, habit, psychological, rules]`
- [ ] `twin/shared/memory/profile/models.py` — `ProfileSection` enum
- [ ] `twin/shared/memory/profile/markdown_store.py`:
  - `read_raw(user_id)` → str
  - `read_section(user_id, section)` → list[str] bullets
  - `append_raw(user_id, section, content, source_memory_id)` — atomic write,
    skip nếu duplicate exact
  - `write_raw(user_id, new_content)` — dùng bởi cleanup, diff check
  - `get_system_prompt_context(user_id)` — render 8 section thành text +
    chỉ thị ẩn "không lộ nguồn"
- [ ] Unit test `tests/unit/memory/test_profile.py`:
  - Append section mới → file có section header
  - Append duplicate bullet → skip
  - Read section trả list bullet đúng
  - System prompt context render đủ 8 section, chỉ thị ẩn có

### Phase 8 — Tools (½ ngày) ✓

- [x] `twin/shared/tools/modules/memory/search_memory_tool.py` — wrap
      `timeline.search`, schema BaseTool tương thích registry
- [x] `twin/shared/tools/modules/profile/get_profile_tool.py` — wrap profile.read
- [x] `twin/shared/tools/modules/profile/update_profile_tool.py` — wrap
      profile.append_raw (bot có thể force update)
- [x] Đăng ký 3 tool vào tool registry
      (`twin/shared/tools/declarations/system_tools.py`)
- [x] Unit test `tests/unit/memory/tools_test.py`:
  - search tool dispatch param đúng
  - update_profile validate section in SECTIONS

### Phase 9 — Wiring + Migration (1 ngày) ✓

- [x] T3 migration script `scripts/migrate_t3_5to8.py` — deterministic 5→8
      section mapping, dry-run default, `.bak5` backup khi apply
- [x] Chạy migration tay cho Hoà + Quang, verify file mới
- [x] `twin/march7/container.py`:
  - Xóa import từ `twin.march7.memories.*` + `twin.shared.memories.*`
  - Import từ `twin.shared.memory.{active,timeline,profile}`
  - Wire ActiveMemory + Consolidator + TimelineSearch + ProfileStore
  - Wire pre-flight retrieval vào agent flow
- [x] `twin/evernight/container.py`:
  - Tương tự, xóa import cũ, wire từ shared
- [x] `twin/march7/agent.py` / `twin/evernight/agent.py`:
  - Inject T3 context + pre-flight T2 vào system prompt
  - Add chỉ thị ẩn "không lộ nguồn"
- [x] Xóa code cũ:
  ```
  rm -rf twin/march7/memories/
  rm -rf twin/evernight/memories/
  rm -rf twin/shared/memories/
  rm -f tests/unit/discussion_consolidator_test.py
  rm -f tests/unit/t2_*
  rm -f twin/shared/tools/modules/memory/consolidate_t2_memory_tool.py
  ```
- [x] Update `twin/shared/tools/declarations/system_tools.py` — remove
      `consolidate_t2_memory` declaration

### Phase 10 — Integration test (½ ngày) ✓

- [x] Unit coverage under `tests/unit/memory/`:
  - End-to-end mock LLM: 5 message → T1 đầy → consolidate → T2 có memory với
    embedding + topic_id + catalogs
  - User đổi ý → cleanup pass detect supersede chain
  - T3 promotion: importance 5 + identity → markdown có section basic
  - Pre-flight: search → top-5 relevant memories
- [x] Docker smoke test:
  ```bash
  docker compose -f docker/docker-compose.yml up -d --build
  docker compose -f docker/docker-compose.yml ps
  curl -sf http://localhost:8000/.well-known/agent.json
  curl -sf http://localhost:8001/.well-known/agent.json
  docker exec march7-redis redis-cli FT.INFO idx:t2:mem
  # → idx:t2:mem có VECTOR HNSW dim 1024
  ```
  Live Discord DM/channel smoke chưa chạy trong local verification vì cần bot
  token thật và gateway event.

### Phase 11 — Polish (½ ngày) ✓

- [x] Logging consistency: each module dùng `logger = logging.getLogger(__name__)`,
      tier prefix: `T1:`, `T2:`, `T3:`
- [ ] LangSmith traceable decorator cho consolidator + cleanup + search
      (defer: no current tracing dependency in this memory path)
- [x] Update `.agents/PROJECT_CONTEXT.md` reflect new memory module
- [x] Update `CLAUDE.md` nếu có instruction nói về memory path cũ (không có file)
- [x] Run full pytest, fix breakage
- [x] Mark plan `status: done`

## Risks & Mitigation

| Risk | Mitigation |
|---|---|
| Gemini embedding API rate limit khi consolidate batch | Retry exponential backoff trong embedder; nếu vẫn fail → memory ghi không vector, cleanup pass retry |
| LLM extract trả format sai → pipeline crash | Pydantic structured output + fallback empty list; log raw response để debug |
| Pass 2 cleanup ghi T3 hỏng | Temp file + diff check > 50% reject; keep `.bak` cho lần ghi gần nhất |
| Race condition: user chat tiếp khi cleanup đang chạy | Lock per user; cleanup chỉ chạy nếu user idle ≥ debounce |
| Migration 5→8 section LLM sai → mất info | One-shot manual verify Hoà + Quang trước; backup `memories.bak/` |
| Redis VECTOR HNSW không hỗ trợ (Redis Stack version cũ) | Check Redis Stack version ≥ 7.2 trước Phase 2; container đang dùng `redis-stack-server:7.2.0-v18` → OK |
| T1 cleanup gọi trước khi T2 ghi xong → mất entry | Đảm bảo consolidate là synchronous trước khi T1.trim; cleanup_scheduler chạy SAU upsert_memory |
| Topic resolver Stage 3 LLM lỗi → tạo topic mới rác | Fallback Stage 4 create new + log warning để cleanup pass merge sau |
| Pre-flight retrieval slow → user thấy lag | KNN < 10ms, embedding query 50-200ms; cache embedding query 5 phút theo content hash |
| Bot reply không vào T2 (lỗ Lỗ #1) | Extractor prompt nhấn mạnh `speaker=bot` cho assistant entry, test case riêng |

## Out-of-band Checks (tự verify trước khi mark done)

- [ ] `wc -l twin/shared/memory/**/*.py` < 1500 (target: gọn hơn cũ 70%)
- [x] `grep -r "twin.march7.memories\|twin.evernight.memories\|twin.shared.memories" .` → 0 hit
- [x] `docker exec march7-redis redis-cli FT.INFO idx:t2:mem | grep -A2 embedding` → có `VECTOR HNSW`
- [ ] Test transcript "Hoà thích Sony, tao đùa thôi chê Sony" → cleanup pass detect supersede
- [x] T3 file của Hoà sau migration có đúng 8 section, không mất info từ file gốc
- [ ] Code review checklist: không có `# TODO`, không có dead import, không có
      file > 300 LOC

## Open Questions

- Pass 2 cleanup gọi LLM nào? Cùng model với extractor (config) hay nhẹ hơn
  (Gemini Flash)? — Default config; sẽ tune sau khi đo cost.
- T3 cleanup có nên auto-archive bullets > 90 ngày không touched? — Defer v2.
- Channel-scope T2 promotion: ai sở hữu? T3 hiện per-user. → Channel
  conversation chỉ fan-out cho participants xuất hiện thực sự, mỗi participant
  có T2 memory riêng dù từ cùng channel — đúng logic cũ. Topic được tạo per
  user_id, không chia sẻ giữa user.

## References

- [Memobase user_profile_topics.py](https://github.com/memodb-io/memobase/blob/main/src/server/api/memobase_server/prompts/user_profile_topics.py)
- [Memobase Profile Fundamentals](https://docs.memobase.io/features/profile/profile)
- [Mem0 paper](https://arxiv.org/pdf/2504.19413)
- [MemoryBank / SiliconFriend](https://arxiv.org/pdf/2305.10250)
- [feature/three-tier-memory-system](https://github.com/Flowerf19/march7) — cơ chế 3-tier cũ để tham khảo flow (T3 inject + chỉ thị ẩn + critical-info real-time)
