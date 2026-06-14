---
status: draft
created: 2026-06-14
last_updated: 2026-06-14
---

# Fix Memory 3 Tầng — T2 Unification, Double Trim, Channel Scope, Docs

## Summary

Sau refactor đơn giản hóa (commits `a28c1d3`, `37630e3`, `7c48933`), memory 3 tầng còn 4 lỗi kiến trúc cần fix:

1. **T2 split (read ≠ write)**: `ConsolidateMemoryTool` ghi vào `TimelineSummaryStore`, nhưng `SharedMemoryManager._preflight_context` đọc qua `TimelineSearch` → `TimelineStore`. `TimelineStore.upsert_memory` có 0 caller; `TimelineSummaryStore.search` có 0 caller.
2. **Double trim T1**: `ConsolidateMemoryTool.execute` trim T1, rồi `SharedMemoryManager.consolidate_scope` lại trim T1.
3. **Channel scope bị block**: `handle_consolidate_discussion_task` chỉ chấp nhận `scope="user"`; `ConsolidateMemoryTool` hardcode `"user"`.
4. **Docs stale**: `README.md` và `PROJECT_CONTEXT.md` vẫn nói về `TimelineStore`, `T2Memory`, `Consolidator` cũ.

Hướng fix: xóa `TimelineStore`/`TimelineSearch`/`T2Memory` (dead code), dùng `TimelineSummaryStore` làm T2 duy nhất, hook vào read path, truyền `scope`/`scope_id` xuống tool, cập nhật docs.

## Success Criteria

- `TimelineStore`, `TimelineSearch`, `T2Memory` biến mất hoàn toàn khỏi codebase.
- `SharedMemoryManager._preflight_context` đọc T2 từ `TimelineSummaryStore.search` (hoặc `get_recent`).
- `ConsolidateMemoryTool.execute` nhận `scope` + `scope_id`, không hardcode `"user"`.
- `handle_consolidate_discussion_task` chấp nhận mọi scope (`user`, `channel`).
- `ConsolidateMemoryTool.execute` không còn trim T1 (trim ở `SharedMemoryManager.consolidate_scope`).
- `README.md` và `.agents/PROJECT_CONTEXT.md` phản ánh kiến trúc hiện tại (không nhắc `TimelineStore`, `T2Memory`, `Consolidator` cũ).
- `pytest` pass, Docker services khởi động healthy.

---

## Tasks

### GOAL-001: Xóa dead code T2 cũ (TimelineStore, TimelineSearch, T2Memory)

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-001 | Xóa `twin/shared/memory/timeline/store.py` (TimelineStore) | | |
| TASK-002 | Xóa `twin/shared/memory/timeline/search.py` (TimelineSearch, format_preflight_for_prompt) | | |
| TASK-003 | Xóa `twin/shared/memory/timeline/models.py` (T2Memory, CATALOGS, helpers) | | |
| TASK-004 | Xóa `twin/shared/memory/timeline/constants.py` (nếu chỉ còn dead constants) | | |
| TASK-005 | Xóa `twin/shared/memory/timeline/__init__.py` hoặc giữ skeleton rỗng | | |
| TASK-006 | Xóa import `TimelineStore`, `TimelineSearch` khỏi `twin/shared/agent/runtime.py` | | |
| TASK-007 | Xóa `timeline_store`, `timeline_search` khỏi `SharedAgentRuntime` dataclass | | |
| TASK-008 | Xóa `timeline_store`, `timeline_search` khỏi `build_shared_agent_runtime` | | |
| TASK-009 | Xóa `timeline_store`, `timeline_search` khỏi `March7Container` | | |
| TASK-010 | Xóa `timeline_store`, `timeline_search` khỏi `EvernightContainer` | | |
| TASK-011 | Xóa `timeline_search` param khỏi `build_tool_registry` (bootstrap.py) | | |
| TASK-012 | Xóa `timeline_search` param khỏi `SYSTEM_TOOL_SPECS` nếu có | | |
| TASK-013 | Chạy `pytest` kiểm tra compile/import errors | | |

**Thay đổi cụ thể:**

- `twin/shared/memory/timeline/store.py` → xóa file.
- `twin/shared/memory/timeline/search.py` → xóa file. Hàm `format_preflight_for_prompt` chuyển sang `twin/shared/memory/manager.py` hoặc `twin/shared/memory/timeline_summary_store.py` (định nghĩa lại để format `TimelineSummary` dict thay vì `T2Memory`).
- `twin/shared/memory/timeline/models.py` → xóa file. Các constant `CATALOGS`, `T3_PROMOTABLE`, `CATALOG_TO_T3` chuyển sang `twin/shared/memory/timeline_summary_store.py` hoặc `twin/shared/memory/profile/` nếu cần.
- `twin/shared/memory/timeline/constants.py` → xóa nếu không còn ai import.
- `twin/shared/memory/timeline/__init__.py` → giữ skeleton rỗng hoặc xóa nếu không còn import.
- `twin/shared/agent/runtime.py`:
  - Xóa import `TimelineStore`, `TimelineSearch`.
  - Xóa field `timeline_store`, `timeline_search` khỏi `SharedAgentRuntime`.
  - Xóa dòng tạo `TimelineStore`, `TimelineSearch` trong `build_shared_agent_runtime`.
  - Xóa `timeline_store`, `timeline_search` khỏi return value.
- `twin/march7/container.py`: Xóa `self.timeline_store`, `self.timeline_search`.
- `twin/evernight/container.py`: Xóa `self.timeline_store`, `self.timeline_search`.
- `twin/shared/tools/registry/bootstrap.py`: Xóa `timeline_search` khỏi `dependencies` dict và `build_tool_registry` signature.

**Lưu ý**: `format_preflight_for_prompt` cần được định nghĩa lại vì nó hiện nhận `list[T2Memory]`. Sau khi xóa `T2Memory`, nó sẽ nhận `list[dict]` (từ `TimelineSummaryStore.search` hoặc `get_recent`).

### GOAL-002: Hook TimelineSummaryStore vào read path (T2 preflight)

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-014 | Thêm `timeline_summary_store` vào `SharedMemoryManager.__init__` | | |
| TASK-015 | Sửa `SharedMemoryManager._preflight_context` để dùng `TimelineSummaryStore` | | |
| TASK-016 | Định nghĩa lại `format_preflight_for_prompt` để format `TimelineSummary` dict | | |
| TASK-017 | Truyền `timeline_summary_store` vào `SharedMemoryManager` từ `runtime.py` | | |
| TASK-018 | Truyền `timeline_summary_store` vào `SharedMemoryManager` từ `March7Container` | | |
| TASK-019 | Truyền `timeline_summary_store` vào `SharedMemoryManager` từ `EvernightContainer` | | |
| TASK-020 | Chạy `pytest` kiểm tra | | |

**Thay đổi cụ thể:**

- `twin/shared/memory/manager.py`:
  - `__init__`: thêm param `timeline_summary_store: Any | None = None`.
  - `_preflight_context`: thay `self.timeline_search.preflight(...)` bằng logic mới:
    ```python
    async def _preflight_context(self, user_id: str, current_query: str) -> str:
        if self.timeline_summary_store is None or not current_query:
            return ""
        try:
            query_embedding = await self.timeline_summary_store.embedding_service.get_embedding(current_query)
            summaries = await self.timeline_summary_store.search(user_id, query_embedding, limit=5)
            return format_preflight_for_prompt(summaries)
        except Exception as exc:
            logger.debug("T2: preflight failed user=%s: %s", user_id, exc)
            return ""
    ```
  - **Vấn đề**: `SharedMemoryManager` không có `embedding_service`. Cần truyền `embedding_service` vào `SharedMemoryManager` HOẶC để `TimelineSummaryStore` tự embed. Cách đơn giản hơn: thêm `embedding_service` vào `SharedMemoryManager.__init__`.
  - `format_preflight_for_prompt` định nghĩa lại trong `manager.py`:
    ```python
    def format_preflight_for_prompt(summaries: list[dict]) -> str:
        if not summaries:
            return ""
        lines = ["## Ngữ cảnh nhớ liên quan (dùng tự nhiên, không lộ nguồn)"]
        for s in summaries:
            content = s.get("content", "")
            if len(content) > 240:
                content = content[:240] + "…"
            lines.append(f"- {content}")
        return "\n".join(lines)
    ```
- `twin/shared/agent/runtime.py`:
  - Truyền `timeline_summary_store` vào `SharedMemoryManager(...)`.
  - Truyền `embedding_service` vào `SharedMemoryManager(...)` (nếu cần cho preflight embed).
- `twin/march7/container.py`:
  - Truyền `timeline_summary_store` (từ `self.runtime.timeline_summary_store`? Không, March7 không tạo `TimelineSummaryStore`). Cần tạo `TimelineSummaryStore` trong `March7Container.initialize()` hoặc trong `build_shared_agent_runtime`.
  - **Quyết định**: Tạo `TimelineSummaryStore` trong `build_shared_agent_runtime` (vì cả March7 và Evernight đều cần đọc T2). Hoặc tạo riêng trong mỗi container. Để minimal: tạo trong `build_shared_agent_runtime`.
- `twin/evernight/container.py`:
  - Evernight đã tạo `TimelineSummaryStore` riêng. Cần đảm bảo `SharedMemoryManager` dùng cùng instance. Truyền vào `build_shared_agent_runtime` hoặc set sau khi tạo.

**Quyết định kiến trúc**: `TimelineSummaryStore` nên được tạo trong `build_shared_agent_runtime` (shared), giống như `TimelineStore` cũ. Cả March7 và Evernight đều cần đọc T2. Evernight cần ghi T2. Dùng cùng Redis client (timeline_redis_client).

### GOAL-003: Sửa double trim T1

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-021 | Xóa đoạn trim T1 trong `ConsolidateMemoryTool.execute` (dòng 184-186) | | |
| TASK-022 | Giữ trim T1 trong `SharedMemoryManager.consolidate_scope` (dòng 167-177) | | |
| TASK-023 | Verify `ConsolidateMemoryTool.execute` không còn side-effect trim | | |

**Thay đổi cụ thể:**

- `twin/evernight/tools/consolidate_memory_tool.py`:
  - Xóa dòng 184-186:
    ```python
    # 7. Trim T1
    entry_ids = [e.entry_id for e in t1_entries]
    await self.memory_manager.t1.trim("user", user_id, entry_ids)
    ```
  - Cập nhật comment bước 8 → bước 7 (vì đã xóa 1 bước).
  - `messages_summarized` trong return vẫn giữ `len(t1_entries)` để `SharedMemoryManager` biết trim bao nhiêu.

### GOAL-004: Support channel scope trong consolidation

| ID | Task | Done | Date |
|----|------|------|
| TASK-024 | Sửa `ConsolidateMemoryTool.parameters_schema` thêm `scope` và `scope_id` | | |
| TASK-025 | Sửa `ConsolidateMemoryTool.execute` nhận `scope` + `scope_id`, thay `user_id` | | |
| TASK-026 | Sửa `ConsolidateMemoryTool.execute` đọc T1 theo scope/scope_id | | |
| TASK-027 | Sửa `handle_consolidate_discussion_task` bỏ block `scope != "user"` | | |
| TASK-028 | Sửa `EvernightAgent.consolidate_via_tool` truyền `scope` + `scope_id` | | |
| TASK-029 | Sửa `ConsolidationClient.consolidate_scope` truyền `scope` + `scope_id` | | |
| TASK-030 | Sửa `SharedMemoryManager.consolidate_scope` để pass `scope`/`scope_id` đúng | | |
| TASK-031 | Chạy `pytest` kiểm tra | | |

**Thay đổi cụ thể:**

- `twin/evernight/tools/consolidate_memory_tool.py`:
  - `parameters_schema`: thay `user_id` bằng `scope` (string) và `scope_id` (string). `scope` default `"user"`.
  - `execute(self, scope: str, scope_id: str, reason: str, max_messages: int = 200)`:
    - `scope_id = str(scope_id or "").strip()`
    - `scope = str(scope or "user").strip()`
    - Đọc T1: `t1_entries = await self.memory_manager.t1.get_context(scope, scope_id, limit=max_messages)`
    - Đọc profile: `profile_text = await self.memory_manager.profile.read_raw(scope_id)` (vẫn dùng scope_id làm user_id cho profile; channel scope có thể không có profile → handle gracefully)
    - Store summary: `await self.timeline_summary_store.store_summary(user_id=scope_id, ...)` (giữ `user_id` làm key trong store, dù scope là channel)
    - Trim T1: **đã xóa** (GOAL-003)
- `twin/evernight/server/a2a_server.py`:
  - `handle_consolidate_discussion_task`:
    - Bỏ block `if not user_id` (dòng 92-101).
    - Truyền `scope` và `scope_id` xuống `agent.consolidate_via_tool`.
- `twin/evernight/agent.py`:
  - `consolidate_via_tool`: thêm param `scope: str = "user"`, `scope_id: str = ""`.
  - Truyền `scope` và `scope_id` vào `tool.execute(...)`.
- `twin/shared/memory/consolidation_client.py`:
  - `consolidate_scope` đã truyền `scope` và `scope_id` trong payload — không cần sửa.
- `twin/shared/memory/manager.py`:
  - `consolidate_scope` đã nhận `scope` và `scope_id` — không cần sửa.

**Edge case**: `scope="channel"`, `scope_id="channel_123"`. `read_raw` có thể fail vì không có profile cho channel. Cần try/except và bỏ qua profile context nếu fail.

### GOAL-005: Cập nhật docs

| ID | Task | Done | Date |
|----|------|------|
| TASK-032 | Sửa `README.md` — bỏ nhắc `TimelineStore`, `T2Memory`, `Consolidator` cũ | | |
| TASK-033 | Sửa `.agents/PROJECT_CONTEXT.md` — phản ánh kiến trúc T2 mới (`TimelineSummaryStore`) | | |
| TASK-034 | Verify docs không còn reference đến dead code | | |

**Thay đổi cụ thể:**

- `README.md`:
  - Dòng 10: "Memory 3 tầng: T1 Redis active, T2 Redis Stack semantic/vector, T3 Markdown profile" → giữ nguyên, nhưng bỏ chi tiết `T2Memory`/`T2Topic` nếu có.
  - Phần "Vòng đời (A2A Consolidation)" step 3: "ghi vào T2/T3" → "ghi vào `TimelineSummaryStore` (T2) và `MarkdownProfileStore` (T3)".
  - Bỏ reference đến `Consolidator`, `Extractor`, `TopicResolver`.
- `.agents/PROJECT_CONTEXT.md`:
  - Dòng 91: "`TimelineStore`, và `TimelineSearch`" → "`TimelineSummaryStore`".
  - Dòng 100: "writes to `TimelineStore` / `MarkdownProfileStore`" → "writes to `TimelineSummaryStore` / `MarkdownProfileStore`".
  - Dòng 101-102: Bỏ "`T2Memory` and `T2Topic` are stored as Redis JSON with RediSearch `VECTOR HNSW` indexes `idx:t2:mem` and `idx:t2:topic`" → thay bằng "`TimelineSummaryStore` stores conversation summaries as Redis HASH with RediSearch `VECTOR HNSW` index `timeline_summaries`".
  - Dòng 102: "Legacy removed" — cập nhật danh sách đã xóa.

---

## Thứ tự thực hiện

1. **GOAL-003** (TASK-021..023): Xóa double trim trong tool — an toàn nhất, không ảnh hưởng read path.
2. **GOAL-004** (TASK-024..031): Support channel scope — sửa tool signature + A2A handler.
3. **GOAL-002** (TASK-014..020): Hook `TimelineSummaryStore` vào read path — cần đảm bảo tool đã ghi đúng trước.
4. **GOAL-001** (TASK-001..013): Xóa dead code `TimelineStore`/`TimelineSearch`/`T2Memory` — làm sau cùng để tránh break build giữa chừng.
5. **GOAL-005** (TASK-032..034): Cập nhật docs — làm cuối cùng.

## Test/Verify

- `pytest tests/unit/ -v` — pass toàn bộ.
- `pytest tests/integration/ -v` — pass nếu có.
- `docker compose -f docker/docker-compose.yml up -d --build` — services healthy.
- `curl -sf http://localhost:8000/.well-known/agent.json` — OK.
- `curl -sf http://localhost:8001/.well-known/agent.json` — OK.
- Manual: gửi 10 message → T1 đầy → consolidation trigger → verify `TimelineSummaryStore` có entry mới.

## Risk & Mitigation

| Risk | Mitigation |
|------|------------|
| Xóa `TimelineStore`/`TimelineSearch` nhưng còn import ẩn | Chạy `grep -r "TimelineStore\|TimelineSearch\|T2Memory" twin/` sau mỗi task. |
| `TimelineSummaryStore.search` chưa được test với real Redis | `pytest` có integration test; nếu không, manual verify với Docker. |
| Channel scope `read_raw` fail vì không có profile | Try/except trong `ConsolidateMemoryTool`, bỏ qua profile nếu fail. |
| `format_preflight_for_prompt` đổi signature break caller | Chỉ có 1 caller (`_preflight_context`), sửa cùng lúc. |
| `SharedMemoryManager` thêm param break container wiring | Sửa cả 3 container (March7, Evernight, runtime) trong cùng 1 commit. |
| T2 data cũ (Redis JSON `t2:mem:*`) bị orphan | Không xóa data cũ trong plan này; chỉ xóa code path. Data cũ sẽ tự TTL hết. |

## Assumptions

- `TimelineSummaryStore` đã hoạt động đúng (write path đã chạy qua tool).
- `TimelineSummaryStore.search` trả về `list[dict]` với key `"content"`.
- `TimelineSummaryStore.get_recent` cũng trả về `list[dict]` tương tự.
- `SharedMemoryManager` được phép thêm dependency `embedding_service` và `timeline_summary_store`.
- Không cần backward compatibility với `T2Memory` model (đã refactor xong).
