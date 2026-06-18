---
status: done
created: 2026-06-15
last_updated: 2026-06-15
---

# T2 Memory Rewrite — Topic-Scoped Summaries + Hybrid Search + m-e5-small

## Summary

Rewrite tầng T2 từ mô hình "1 consolidate = 1 flat summary" sang "1 consolidate = N topic summaries". Search chuyển từ pure KNN sang hybrid (KNN + Redis BM25, fused bằng RRF). Model embedding đổi từ Qwen 1024-dim sang `multilingual-e5-small` 384-dim qua LM Studio. Toàn bộ thay đổi tập trung ở 5 file core; T1, T3, A2A không đổi.

**Verified wiring (codegraph):**
- `get_embedding` có đúng 3 caller: `consolidate_memory_tool.py` (document), `manager.py:244` (query), `search_memory_tool.py:105` (query)
- `TimelineSummaryStore.__init__` nhận `embedding_dim=1024` hardcoded tại `runtime.py:74` — không đọc từ Config
- `build_shared_agent_runtime` là nơi duy nhất khởi tạo store, dùng chung cho cả march7 và evernight
- Cache key của embedding = raw text (không có prefix) — đây là rủi ro khi thêm e5 prefix

**Success criteria:**
1. Evernight tạo N summary/topic mỗi lần consolidate (N≥1, N≤5 thực tế)
2. Hybrid search trả kết quả có cả semantic + text match
3. Redis index 384-dim, BM25 hoạt động trên field `summary` (TEXT)
4. `_preflight_context` trong manager vẫn hoạt động (query prefix "query: ")
5. Tests pass sau khi cập nhật

---

## Tasks

### GOAL-001: Đổi embedding model sang m-e5-small 384-dim + thêm asymmetric prefix

> Rủi ro cao nhất: prefix e5 sai sẽ gây dim/semantic mismatch im lặng. Làm trước, test ngay.

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-001 | **`openai_embedding_service.py`**: thêm param `text_prefix: str = ""` vào `__init__`. Trong `get_embedding`, apply prefix trước khi gọi API: `prefixed = f"{self.text_prefix}{text}"`. Cache key dùng `prefixed` (không phải `text` gốc) để tránh collision query vs passage. | ✅ | 2026-06-15 |
| TASK-002 | **`embedding_factory.py:43`**: khi tạo `OpenAIEmbeddingService`, không truyền prefix — service tạo ra là "neutral", không có prefix mặc định. Prefix được inject ở caller-level (TASK-003/004). | ✅ | 2026-06-15 |
| TASK-003 | **`consolidate_memory_tool.py:168`** (document side): đổi `await self.embedding_service.get_embedding(timeline_summary)` thành `await self.embedding_service.get_embedding(f"passage: {timeline_summary}")`. Đây là điểm duy nhất store document embedding vào T2. | ✅ | 2026-06-15 |
| TASK-004 | **`manager.py:244`** (query side): đổi `await self.embedding_service.get_embedding(current_query)` thành `await self.embedding_service.get_embedding(f"query: {current_query}")`. | ✅ | 2026-06-15 |
| TASK-005 | **`search_memory_tool.py:105`** (query side): đổi `await self.embedding_service.get_embedding(query)` thành `await self.embedding_service.get_embedding(f"query: {query}")`. | ✅ | 2026-06-15 |
| TASK-006 | **Env vars** cần đổi (docker/march7 và docker/evernight): `EMBEDDING_PROVIDER=openai_compat`, `EMBEDDING_API_URL=http://host.docker.internal:1234/v1`, `EMBEDDING_MODEL_NAME=multilingual-e5-small`, `EMBEDDING_VECTOR_SIZE=384`, `EMBEDDING_API_KEY=lm-studio` (LM Studio dùng bất kỳ key nào). Cập nhật `.env.example` hoặc docker-compose. | ✅ | 2026-06-15 |
| TASK-007 | **`runtime.py:74`**: đổi hardcoded `embedding_dim=1024` thành `embedding_dim=Config.EMBEDDING_VECTOR_SIZE`. Single source of truth từ env. | ✅ | 2026-06-15 |

---

### GOAL-002: Migration — flush index cũ, FT.CREATE lại schema mới

> Phải chạy TRƯỚC khi khởi động lại service với code mới, nếu không `initialize()` sẽ detect index cũ còn tồn tại (FT.INFO thành công) và skip tạo lại.

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-008 | Viết migration script (hoặc one-liner redis-cli) để: (1) `FT.DROPINDEX timeline_summaries DD` — xóa index + data; (2) xóa mọi key `timeline:summary:*` nếu DD flag không xóa data. Script: `redis-cli -n <TIMELINE_REDIS_DB> FT.DROPINDEX timeline_summaries DD && redis-cli -n <TIMELINE_REDIS_DB> --scan --pattern 'timeline:summary:*' | xargs redis-cli -n <TIMELINE_REDIS_DB> DEL`. | ✅ | 2026-06-15 |
| TASK-009 | **`timeline_summary_store.py:56-76` (`initialize`)**: cập nhật `FT.CREATE` schema thêm các field mới: `topic TAG`, `topic_display TEXT`, `summary TEXT`, `version NUMERIC`, đổi tên `content` → `summary` (hoặc thêm `summary` riêng — xem TASK-010), đổi `DIM` sang `self.embedding_dim` (đã dùng đúng rồi). Thêm `SORTABLE` cho `importance`. Full schema mới xem phần Interfaces bên dưới. | ✅ | 2026-06-15 |
| TASK-010 | **`TimelineSummary` dataclass**: thêm fields `topic: str`, `topic_display: str`, `version: int = 2`. Rename field `content` → `summary` (breaking change — tất cả accessor cần cập nhật). `to_dict()` emit đúng field names. | ✅ | 2026-06-15 |

---

### GOAL-003: Cập nhật `store_summary` — nhận topic, lưu schema v2

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-011 | **`store_summary` signature**: đổi thành `store_summary(self, user_id, summary, embedding, *, topic="general", topic_display="", importance=3) -> str`. Field `hset mapping` bổ sung `topic`, `topic_display`, `summary` (thay `content`), `version=2`. | ✅ | 2026-06-15 |
| TASK-012 | **`_pack_embedding`**: không đổi logic, nhưng kiểm tra `len(embedding) == self.embedding_dim` — log warning nếu sai dim thay vì silently pack sai bytes. | ✅ | 2026-06-15 |
| TASK-013 | **`get_recent`**: cập nhật field name `content` → `summary` trong kết quả trả về (hoặc alias cả hai để backward compat với `_format_memories`). | ✅ | 2026-06-15 |

---

### GOAL-004: Hybrid search — KNN + BM25 + RRF

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-014 | **`search` method mới** trong `TimelineSummaryStore`: tách thành `search_knn(user_id, query_embedding, limit, topic_filter=None)` và `search_bm25(user_id, query_text, limit, topic_filter=None)`. `topic_filter` nếu có → thêm `@topic:{<val>}` vào query string. | ✅ | 2026-06-15 |
| TASK-015 | **`_rrf_fuse(knn_results, bm25_results, k=60, limit=5)`**: pure function ~15 dòng. Input: 2 list[dict] mỗi phần tử có `summary_id`. Output: list[dict] đã merge+rerank. Công thức: `score(d) = Σ 1/(k + rank_in_list)`. Dedup bằng `summary_id`. Merge dict từ cả 2 source (ưu tiên KNN dict khi conflict). | ✅ | 2026-06-15 |
| TASK-016 | **`search` method public** (giữ nguyên signature với caller): `search(user_id, query_embedding, limit, *, query_text=None, topic_filter=None)`. Nếu `query_text` có → hybrid (gọi cả knn + bm25 → rrf_fuse). Nếu không → chỉ KNN (backward compat với `_preflight_context` hiện tại). | ✅ | 2026-06-15 |
| TASK-017 | **BM25 Redis query**: `FT.SEARCH timeline_summaries "@user_id:{<uid>} <query_text>" SCORER BM25 WITHSCORES LIMIT 0 <limit> DIALECT 2`. KHÔNG dùng `SORTBY __score` (RediSearch không có field đó) — relevance là thứ tự mặc định khi không SORTBY; dùng `WITHSCORES` để lấy điểm. Verify scorer name bằng docs Redis khi code (Redis 8 mặc định `BM25STD`). `query_text` phải escape ký tự đặc biệt (dùng `re.sub(r'[^a-zA-Z0-9\sÀ-ɏẠ-ỹ]', ' ', text)` trước khi query). | ✅ | 2026-06-15 |

---

### GOAL-005: Cập nhật `SearchMemoryTool` — thêm mode hybrid

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-018 | **`parameters_schema`**: thêm `"hybrid"` vào enum của `mode`. Thêm param `topic` (string, optional) cho soft topic filter. | ✅ | 2026-06-15 |
| TASK-019 | **`execute` logic**: `auto` + có `query` → `"hybrid"`. `hybrid` → gọi `timeline_summary_store.search(..., query_text=query, topic_filter=topic)`. Kết quả của hybrid trả về dict với field `summary` (thay `content`) — cập nhật `_format_memories` / `_field` để đọc đúng. | ✅ | 2026-06-15 |
| TASK-020 | **`_format_memories`**: cập nhật để đọc field `summary` (không chỉ `content`). Thêm `topic` vào metadata display nếu có. | ✅ | 2026-06-15 |

---

### GOAL-006: Cập nhật `ConsolidateMemoryTool` — Evernight sinh N topic summaries

> Đây là thay đổi lớn nhất về prompt engineering. Rủi ro: LLM không parse được JSON N-topics.

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-021 | **`_SUMMARIZER_PROMPT` mới**: thay `timeline_summary` (string) bằng `topics` (array) + cờ `has_meaningful_content` (bool). Prompt yêu cầu LLM: (1) lọc noise (chào hỏi, emoji, phiếm, tạm thời), (2) nhóm messages theo topic, (3) với mỗi topic → 1-2 câu summary ngắn. Return JSON: `{"has_meaningful_content": true, "topics": [{"topic": "work", "topic_display": "Dự án X", "summary": "...", "importance": 3}], "profile_updates": {...}}`. Rules: **topic taxonomy TỰ DO** (LLM tự đặt slug lowercase+underscore, không fixed enum); tối đa 5 topics; topic_display tự do. Nếu session toàn noise → `has_meaningful_content=false`, `topics=[]`. | ✅ | 2026-06-15 |
| TASK-022 | **`execute` step 5** (thay store 1 summary bằng loop N topics): nếu `data.get("has_meaningful_content") is False` hoặc `topics` rỗng → **skip store** (không tạo entry rác), trả `topics_stored=0`. Ngược lại parse `data.get("topics", [])`. Với mỗi topic_item: `embedding = await self.embedding_service.get_embedding(f"passage: {topic_item['summary']}")`, rồi `await self.timeline_summary_store.store_summary(user_id=scope_id, summary=topic_item["summary"], embedding=embedding, topic=topic_item.get("topic", "general"), topic_display=topic_item.get("topic_display", ""), importance=topic_item.get("importance", 3))`. Collect `summary_ids = []`. | ✅ | 2026-06-15 |
| TASK-023 | **Fallback JSON parse**: nếu LLM trả về `timeline_summary` (format cũ) thay vì `topics`, convert sang `[{"topic": "general", "topic_display": "Tổng hợp", "summary": timeline_summary, ...}]`. Giúp migration mượt hơn khi rollback. | ✅ | 2026-06-15 |
| TASK-024 | **Return dict**: cập nhật `"summary_id"` → `"summary_ids"` (list), `"topics_stored"` (count). | ✅ | 2026-06-15 |

---

### GOAL-007: `format_preflight_for_prompt` — cập nhật field name

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-025 | **`manager.py:13-22` (`format_preflight_for_prompt`)**: hiện đọc `s.get("content", "")` — đổi thành `s.get("summary") or s.get("content", "")` để backward compat với data cũ chưa migrate. | ✅ | 2026-06-15 |
| TASK-026 | **`_preflight_context` tại `manager.py:244` → NÂNG LÊN HYBRID** (quyết định đã chốt): `current_query` text đã có sẵn ngay tại đây → đổi call thành `search(user_id, query_embedding, limit=5, query_text=current_query)`. Đây là đường recall chạy MỖI tin nhắn — phải có BM25 mới đạt mục tiêu. Diff ~1 dòng. Embedding query đã prefix "query: " ở TASK-004. | ✅ | 2026-06-15 |

---

### GOAL-008: Tests

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-027 | **`tests/unit/memory/tools_test.py`**: cập nhật `FakeEmbeddingService.get_embedding` trả về `[0.1] * 384` (thay 1024). Cập nhật `FakeTimelineSearch.search` nhận thêm `query_text=None, topic_filter=None`. Thêm test case `mode="hybrid"`. | ✅ | 2026-06-15 |
| TASK-028 | **Unit test cho `_rrf_fuse`**: tạo `tests/unit/memory/test_rrf.py`. Test: (a) kết quả overlap → reranked; (b) chỉ có KNN; (c) chỉ có BM25; (d) empty input. Pure function, không cần async. | ✅ | 2026-06-15 |
| TASK-029 | **Unit test cho `store_summary` v2 schema**: mock redis `hset`, verify mapping có đủ `topic`, `topic_display`, `summary`, `version=2`, không có `keywords`, không có `confidence`. | ✅ | 2026-06-15 |
| TASK-030 | **Unit test cho e5 prefix**: verify `get_embedding("query: foo")` và `get_embedding("passage: foo")` gọi API với text đúng (mock aiohttp). Verify cache key = prefixed text. | ✅ | 2026-06-15 |

---

## Interfaces

### Redis schema v2 (FT.CREATE)

```
FT.CREATE timeline_summaries ON HASH PREFIX 1 timeline:summary:
SCHEMA
  user_id     TAG
  topic       TAG
  topic_display TEXT
  summary     TEXT
  importance  NUMERIC SORTABLE
  created_at  NUMERIC SORTABLE
  version     NUMERIC
  embedding   VECTOR HNSW 6 TYPE FLOAT32 DIM 384 DISTANCE_METRIC COSINE
```

### `store_summary` signature mới

```python
async def store_summary(
    self,
    user_id: str,
    summary: str,
    embedding: list[float],
    *,
    topic: str = "general",
    topic_display: str = "",
    importance: int = 3,
) -> str
```

### LLM prompt output format mới

```json
{
  "topics": [
    {"topic": "work", "topic_display": "Công việc", "summary": "...", "importance": 4},
    {"topic": "interest", "topic_display": "Sở thích", "summary": "...", "importance": 3}
  ],
  "profile_updates": {"basic": [], "work": [...], ...}
}
```

---

## Env vars (docker/.env hoặc docker-compose)

| Var | Giá trị cũ | Giá trị mới |
|-----|-----------|-------------|
| `EMBEDDING_PROVIDER` | `openai_compat` | `openai_compat` (không đổi) |
| `EMBEDDING_API_URL` | `https://dashscope-intl.aliyuncs.com/...` | `http://host.docker.internal:1234/v1` |
| `EMBEDDING_MODEL_NAME` | `text-embedding-v3` | `multilingual-e5-small` |
| `EMBEDDING_VECTOR_SIZE` | `1024` | `384` |
| `EMBEDDING_API_KEY` | DashScope key | `lm-studio` (bất kỳ) |

Cả `docker/march7` và `docker/evernight` đều cần đổi (cả hai dùng chung `build_shared_agent_runtime`).

---

## Test Plan

1. **Trước khi code**: confirm LM Studio đang serve `multilingual-e5-small` tại port 1234. Test thủ công: `curl http://host.docker.internal:1234/v1/embeddings -d '{"model":"multilingual-e5-small","input":"query: test"}' -H 'Content-Type: application/json'` → expect 384-dim vector.
2. **GOAL-001**: chạy `pytest tests/unit/memory/tools_test.py -v` sau TASK-001→007. Verify FakeEmbeddingService trả 384 dim không crash.
3. **GOAL-004**: `pytest tests/unit/memory/test_rrf.py -v` — pure unit, nhanh, không cần Redis.
4. **GOAL-003 + 009**: `pytest tests/unit/memory/` sau khi có test mới cho store schema.
5. **Integration smoke test** (cần Redis Stack): chạy `python -m twin.evernight` → gọi `consolidate_memory` với 5 messages fake → verify Redis có N keys `timeline:summary:*` với field `topic` và `summary` (dùng `redis-cli hgetall timeline:summary:<id>`).
6. **Hybrid search smoke**: gọi `search_memory` với mode=hybrid, query="phim" → expect kết quả từ cả vector + text match.

---

## Thứ tự thực hiện an toàn

```
TASK-006 (env) + TASK-007 (runtime dim)    ← không break gì, chỉ config
  → TASK-008 (migration flush)             ← chạy trên Redis trước khi restart
  → GOAL-001 (prefix e5: TASK-001→005)    ← test ngay với FakeEmbeddingService
  → GOAL-002/003 (schema + store_summary: TASK-009→013)
  → GOAL-004 (hybrid search: TASK-014→017)
  → GOAL-005 (search tool: TASK-018→020)
  → GOAL-006 (consolidate N topics: TASK-021→024)
  → GOAL-007 (format_preflight: TASK-025→026)
  → GOAL-008 (tests: TASK-027→030)
```

---

## Điểm rủi ro

| Rủi ro | Mức | Biện pháp |
|--------|-----|-----------|
| e5 prefix sai (passage vs query nhầm chỗ) | Cao | Verify 3 caller bằng codegraph trước khi commit. Test TASK-030 kiểm tra từng caller. |
| Cache collision: "foo" và "query: foo" cùng key | Trung | TASK-001 đổi cache key = prefixed text. Verify trong test. |
| LLM trả `timeline_summary` (format cũ) thay `topics` | Trung | TASK-023 thêm fallback converter. |
| LLM parse JSON lỗi khi N-topics | Trung | Giữ nguyên `json.JSONDecodeError` handling hiện có. Thêm log rõ raw response. |
| Redis index cũ còn sót (FT.INFO thành công → skip FT.CREATE) | Cao | TASK-008 phải chạy trước restart. Doc rõ trong migration. |
| `_pack_embedding` pack bytes sai dim | Trung | TASK-012 log warning + `_fit_vector` đã có trong base service để trim/pad. |
| BM25 query với ký tự Unicode đặc biệt | Thấp | TASK-017 sanitize query text trước khi gửi Redis. |
| `format_preflight_for_prompt` đọc field `content` không có | Thấp | TASK-025 thêm `or s.get("content", "")` fallback. |

---

## Open Questions

1. ✅ **RESOLVED — Topic taxonomy TỰ DO**: LLM tự đặt slug (lowercase+underscore), không fixed enum. (TASK-021)
2. ✅ **RESOLVED — Session rỗng → SKIP store**: dùng cờ `has_meaningful_content`; toàn noise → không tạo entry. Không enforce min topic. (TASK-021/022)
3. **Cache key với prefix**: cache của `BaseEmbeddingService` dùng `text` làm key. Sau TASK-001 cache key là `f"{prefix}{text}"`. Codegraph xác nhận chỉ 3 caller, tất cả đều đi qua prefix → không có bypass. Vẫn verify khi code.
4. ✅ **RESOLVED — `_preflight_context` NÂNG LÊN HYBRID**: truyền `query_text=current_query`, diff ~1 dòng. (TASK-026)
5. **source_range field**: để sau — không implement trong scope này.

---

## Assumptions

- LM Studio đã được bind `0.0.0.0` (xem memory `lmstudio-docker-bind.md`) và model `multilingual-e5-small` đã load.
- Redis Stack version hỗ trợ BM25 scorer (RediSearch 2.6+). Verify: `redis-cli MODULE LIST` → expect `search` version ≥ 2.6.
- `FT.DROPINDEX ... DD` xóa cả data keys. Nếu Redis version cũ hơn không support `DD` → phải xóa key thủ công.
- Channel scope consolidation (`scope != "user"`) vẫn dùng `scope_id` làm `user_id` trong store — không đổi behavior này.
