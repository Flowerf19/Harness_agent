# Unified Discussion Memory Plan

Plan thống nhất T1 + T2 cho cả 1-1 user chat lẫn multi-user channel discussion. Thay thế plan cũ `channel-discussion-memory.md` (đã đụng tới cả hai tầng nên đổi tên).

## Mục tiêu

- **T1 (Active Memory)**: observe được cả user-scope và channel-scope qua cùng một API (scope param). Bot có thể nghe hội thoại multi-user trong channel cho phép, mà không reply nếu không được gọi.
- **T2 (Episodic/Wiki Memory)**: user-centric — bot nhớ theo USER, không theo channel. Channel chỉ là metadata trong `source_refs`. Bot theo user khắp nơi: Flowerf bàn Python trong `#dev`, mai chat DM bot vẫn nhớ.
- **Event flow unified**: cả user 1-1 và channel discussion đều dùng `SUMMARY_REQUESTED → SUMMARY_COMPLETED/FAILED`. Bỏ flow cũ `TOKEN_LIMIT_REACHED → overflow_queue`.
- **Boundary nghiêm ngặt**: Evernight chạy `DiscussionConsolidator` qua A2A/event. March7 chỉ emit event + cleanup T1 khi nhận confirm.
- **Safe failure**: `SUMMARY_FAILED` không xóa raw, chỉ clear lock + set retry.

## Trạng thái triển khai hiện tại

Cập nhật sau khi hoàn tất wire A2A end-to-end và cleanup legacy ngày 2026-05-25.

### Đã triển khai

- **Phase 1.1 + 1.2**: `MemoryEntry` có `scope/scope_id` + metadata channel; `RamStorage`, `RedisStorage`, `RedisStackStorage` đều scope-aware. Cả March7 và Evernight T1 dùng cùng schema (Evernight cho DM/!9 chat).
- **Phase 1.3 + 2**: `SummaryState`, `SummaryStateRepository`, `SummaryPolicy` (3 trigger: token/message_count/idle, lock semantics). Container cả March7 và Evernight wire policy vào T1.
- **Phase 3**: `ActiveMemoryEvent` còn `SUMMARY_REQUESTED`, `SUMMARY_COMPLETED`, `SUMMARY_FAILED`. **Legacy `TOKEN_LIMIT_REACHED` đã gỡ hoàn toàn** (kể cả enum, handler, fallback path).
- **Phase 4**: Gateway Discord tách `should_observe`/`should_respond`; `AdminChannels` có `ChannelMode` (`observe`/`respond`); converter có `is_reply_to_bot`; `UnifiedChannel` có `guild_id`.
- **Phase 5.1 + 5.2**: `T2Page` có `participants` (TAG indexed), `source_refs`. FT schema thêm `$.participants[*] AS participants TAG`.
- **Phase 5.3 hoàn tất**: `DiscussionConsolidator.consolidate()` trả result dict (status/page_ids/summarized_entry_ids), không emit local. JSON parse được hardened bằng `extract_json_object` (handle markdown fence + bare JSON in prose).
- **Phase 5 A2A wire**: Evernight expose skill `consolidate_discussion`. `EvernightClient.request_consolidation` ở March7 send `tasks/send` với `payload`. Wire qua `Config.EVERNIGHT_A2A_URL` trong `March7Container`. `MemoryManager._handle_summary_requested` gọi A2A roundtrip rồi emit `SUMMARY_COMPLETED`/`SUMMARY_FAILED` local theo result.
- **Phase 6**: T1 `cleanup_summarized` xoá raw entries sau `SUMMARY_COMPLETED`, giữ 3 message cuối. `SUMMARY_FAILED` giữ raw và set `locked_until`.
- **Phase 7**: `build_channel_context` đầy đủ; `MemoryManager.get_context` trả 3-tuple với channel context; agent inject vào system prompt.
- **Phase 8**: `InactivityTrigger` refactor sang dùng `SummaryStateRepository` + `SummaryPolicy` trực tiếp. Mỗi agent chạy instance riêng in-process — March7 scan `("user", "channel")` từ `gateway/__main__.py` (Docker entry), Evernight scan `("user",)` từ `twin/evernight/__main__.py`. `twin/march7/__main__.py` cũng có wiring mirror để local dev hoạt động giống Docker. Bỏ legacy `_scan_inactive_users` và `ConsolidationRunner.run_for_scope` dependency.
- **.gitignore**: thêm exception `!twin/**/memories/**`. New source files dưới `memories/` track được, `__pycache__` re-ignored.

### Chưa hoàn tất / còn rủi ro

- **T2 FT index migration production**: deploy lần đầu cần `FT.DROPINDEX idx:t2:page` rồi restart để recreate với `participants[*]`. `_create_index` skip nếu đã tồn tại. Local dev hiện sạch sau khi reset volume.
- **`MemoryWorker` + `MemoryJobQueue` legacy**: code còn ở Evernight cho compat với tooling cũ push trực tiếp vào queue, nhưng không còn nằm trên hot path. Có thể gỡ ở lượt cleanup sau.
- **`ConsolidationRunner`**: vẫn instantiate trong Evernight `__main__` cho compat, nhưng `run_for_scope("channel")` vẫn chỉ return error (không còn được gọi từ trigger). Có thể gỡ hoặc đơn giản hoá sau.
- **Search side T2**: `SearchMemoryTool` chưa expose filter theo `participants` TAG (đã có index sẵn). Future enhancement.

### Test coverage hiện tại

- `tests/unit/summary_policy_test.py` — 8 test (3 trigger + lock semantics).
- `tests/unit/discussion_consolidator_test.py` — 11 test (single user, channel fan-out, skipped, malformed JSON, markdown fence, merge).
- `tests/unit/inactivity_trigger_test.py` — 5 test (scope iteration, error resilience, scopes filter).
- Tổng `pytest tests/unit`: **66 passed**.

### Verification đã chạy

```bash
python -m compileall twin gateway
pytest tests/unit
DOCKER_BUILDKIT=1 docker compose -f docker/docker-compose.yml build march7 evernight
docker compose -f docker/docker-compose.yml up -d
curl -s http://localhost:8000/.well-known/agent.json
curl -s http://localhost:8001/.well-known/agent.json
```

Kết quả:

- `pytest tests/unit` → **66 passed** (0.31s).
- Cả `march7` và `evernight` container healthy.
- Evernight agent card expose skill `consolidate_discussion`.
- Logs xác nhận `InactivityTrigger started (poll=60s, scopes=('user','channel'))` ở March7 và `scopes=('user',)` ở Evernight.
- Probe synthetic `tasks/send skill=consolidate_discussion` thành công end-to-end: LLM được gọi, trả result dict với `status=skipped` cho transcript ngắn không đáng lưu. JSON parse + return-dict path verified.
- Production Redis state đã có `summary_state:channel:{id}` và `summary_state:user:{id}` từ real Discord traffic — schema mới đang chạy live.

## Kiến trúc tổng quan

```text
Discord message (DM, mention, reply-to-bot, allowed channel)
   │
   ▼
Gateway handler
   - should_observe = is_dm | is_mentioned | is_reply_to_bot | is_observe_channel
   - should_respond = is_dm | is_mentioned | is_reply_to_bot | is_respond_channel
   │
   ▼
T1 ActiveMemoryService
   - observe_user_message(...)     → active_memory:user:{user_id}
   - observe_channel_message(...)  → active_memory:channel:{channel_id}
   │
   ▼
SummaryPolicy.evaluate(scope, scope_id)
   - idle ≥ 30min & messages ≥ 30   → SUMMARY_REQUESTED(reason="idle")
   - messages ≥ 60                  → SUMMARY_REQUESTED(reason="message_count")
   - tokens ≥ threshold             → SUMMARY_REQUESTED(reason="token_limit")
   │
   ▼ (A2A boundary)
Evernight DiscussionConsolidator
   1. Nhận raw entries + scope metadata
   2. Format transcript (mode "1-1" hoặc "multi-user")
   3. LLM summarize → { canonical_topic, summary, key_points,
                         participants, active_participants, ... }
   4. Fan-out: for each active_participant:
        page_id = generate_topic_id(participant_id, canonical_topic)
        existing = T2.lookup_by_page_id(page_id)
        merged = wiki_merge(existing, new) if existing else new
        T2.embed_page(merged)
   │
   ▼ (A2A boundary)
T1 nhận SUMMARY_COMPLETED { summarized_entry_ids, page_ids }
   - Mark last_summarized_entry_id
   - Reset unsummarized_message_count / unsummarized_token_count
   - Clear summary_in_progress
   - Delete raw entries trong window đã summarize
   - Giữ 3-10 message gần nhất (chống đứt mạch)
```

## Bảng quyết định đã chốt

| # | Quyết định | Tác động chính |
|---|---|---|
| 1 | Channel observe **chỉ thuộc March7** | Channel state trong `MARCH7_REDIS_DB=0`. Evernight không observe channel. |
| 2 | T1 storage: **scope param API** | Key đổi từ `active_memory:{user_id}` sang `active_memory:{scope}:{scope_id}`. Breaking key cũ nhưng OK vì T1 TTL 30 phút. |
| 3 | Gateway: **extend `AdminChannels` per-channel mode** | Thêm `ChannelMode` enum (`OBSERVE_ONLY`/`RESPOND_ALLOWED`). Respond trigger thêm `is_reply_to_bot`. |
| 4 | T2: **user-centric**, không channel-centric | `T2Page.user_id = real user_id`. Channel chỉ là metadata trong `source_refs`. |
| 5 | `generate_topic_id(user_id, topic)` **giữ nguyên signature** | Channel discussion fan-out: gọi N lần per active_participant. Backward compat ID T2 cũ. |
| 6 | **Evernight chạy DiscussionConsolidator** | March7 emit event, Evernight subscribe qua A2A. Match boundary `.agents/PROJECT_CONTEXT.md`. |
| 7 | `SearchMemoryTool` **không cần sửa** validation | user_id vẫn là digit (user-centric). Defer mở rộng search tới sau. |
| 8 | **Unified flow** cả 1-1 và channel | Bỏ `TOKEN_LIMIT_REACHED → overflow_queue`. Cả hai dùng `SUMMARY_REQUESTED`. |
| Bonus | LLM trả `active_participants` field | DiscussionConsolidator chỉ fan-out cho user trong list này. |

## Lỗi và điểm dễ quên

- Không observe toàn server. Chỉ observe DM, channel admin enable (mode bất kỳ), mention, reply tin bot.
- Bot reply nếu: DM, mention, reply-to-bot, hoặc channel mode `RESPOND_ALLOWED`.
- Token limit không nên cleanup trực tiếp nữa. Chuyển thành `SUMMARY_REQUESTED`.
- T1 không xóa raw entries khi vừa phát event. **Chỉ cleanup sau `SUMMARY_COMPLETED`**.
- Summary fail không được làm mất memory. Clear lock, set retry/`locked_until`, giữ raw entries.
- T1 không biết schema T2. Đường tích hợp: `T1 → SUMMARY_REQUESTED → DiscussionConsolidator (Evernight) → embed_page() → SUMMARY_COMPLETED → T1 cleanup`.
- T2 prompt phải hỗ trợ 2 mode: 1-1 (user-only transcript) và multi-user (channel discussion).
- `unsummarized_*` counter **reset khi `SUMMARY_COMPLETED`**, không reset ngay khi emit `SUMMARY_REQUESTED` — tránh mất message nếu fail.
- Channel discussion fan-out: 1 LLM call, N embed_page (N = `active_participants.length`). Embedding tính 1 lần share giữa N page.

## Phase 1 — T1 schema mở rộng + scope-aware storage

### 1.1 Mở rộng `MemoryEntry`

```python
# twin/march7/memories/activate_memory/models.py
from typing import Literal

class MemoryEntry(BaseModel):
    """T1 Active Memory entry stored in Redis."""
    
    # Scope identification
    scope: Literal["user", "channel"] = "user"
    scope_id: str                             # = user_id (user-scope) | channel_id (channel-scope)
    
    # Sender info
    user_id: str                              # người gửi (cả user-scope lẫn channel-scope)
    role: str                                 # "user" | "assistant" | "system"
    
    # Channel-scope extras (None cho user-scope)
    author_id: str | None = None
    author_name: str | None = None
    guild_id: str | None = None
    channel_id: str | None = None
    message_id: str | None = None
    reply_to: str | None = None
    
    # Content
    content: str
    tokens: int
    timestamp: datetime = Field(default_factory=get_utc_now)
    entry_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
```

### 1.2 Storage API scope-aware

```python
# twin/march7/memories/activate_memory/storage/base_storage.py
class BaseStorage(ABC):
    @abstractmethod
    async def save_entry(self, entry: MemoryEntry) -> None: ...
    
    @abstractmethod
    async def get_entries(self, scope: str, scope_id: str) -> List[MemoryEntry]: ...
    
    @abstractmethod
    async def get_total_tokens(self, scope: str, scope_id: str) -> int: ...
    
    @abstractmethod
    async def delete_entries(
        self, scope: str, scope_id: str, entry_ids: List[str]
    ) -> None: ...
    
    @abstractmethod
    async def clear_all(self, scope: str, scope_id: str) -> None: ...
```

```python
# RedisStorage helper
def _get_redis_key(self, scope: str, scope_id: str) -> str:
    return f"active_memory:{scope}:{scope_id}"
```

Sửa đồng bộ ở: `RedisStorage`, `RedisStackStorage`, `RamStorage`.

### 1.3 `SummaryState` persistence

```python
class SummaryState(BaseModel):
    scope: str                          # "user" | "channel"
    scope_id: str
    
    last_activity_at: datetime
    last_summarized_at: datetime | None = None
    last_summarized_entry_id: str | None = None
    
    unsummarized_message_count: int = 0
    unsummarized_token_count: int = 0
    
    summary_in_progress: bool = False
    locked_until: datetime | None = None
    retry_count: int = 0
```

Redis key: `summary_state:{scope}:{scope_id}`.

**Persistence**: pure Redis Hash (`HSET`), không qua `RedisStackStorage` adapter — giữ T1 storage layer cho raw entries thuần, SummaryState là sidecar metadata.

### 1.4 Constants cập nhật

```python
# twin/march7/memories/activate_memory/constants.py

# --- Token Management ---
MAX_WORKING_TOKENS = 2000              # User-scope token threshold
CHANNEL_SUMMARY_TOKEN_LIMIT = 2000     # Channel-scope token threshold (tách riêng)
STRUCTURAL_OVERHEAD_TOKENS = 15
TARGET_SAFE_TOKENS = 1000

# --- Summary Policy ---
SUMMARY_IDLE_MINUTES = 30
SUMMARY_MIN_MESSAGES = 30              # min messages khi idle trigger
SUMMARY_MAX_MESSAGES = 60              # hard cap → trigger ngay không cần idle

# --- Timeouts ---
SESSION_TIMEOUT_MINUTES = 30
SUMMARY_LOCK_TTL_MINUTES = 10          # locked_until = now + this khi summary_in_progress

# --- Cleanup ---
KEEP_RECENT_MESSAGES_AFTER_SUMMARY = 3 # giữ 3 msg cuối sau cleanup
```

## Phase 2 — T1 service API

### 2.1 `ActiveMemoryService`

```python
async def observe_user_message(
    self, user_id: str, role: str, content: str
) -> MemoryEntry:
    """Standard user 1-1 chat."""
    # scope="user", scope_id=user_id

async def observe_channel_message(
    self,
    guild_id: str,
    channel_id: str,
    author_id: str,
    author_name: str,
    message_id: str,
    content: str,
    reply_to: str | None = None,
) -> MemoryEntry:
    """Channel ambient observe — không reply, không gọi LLM."""
    # scope="channel", scope_id=channel_id
```

Nhiệm vụ chung sau khi save: gọi `SummaryPolicy.evaluate(scope, scope_id)`.

### 2.2 `SummaryPolicy` (module mới)

```python
# twin/march7/memories/activate_memory/management/summary_policy.py
class SummaryPolicy:
    def __init__(self, storage, state_repo, event_dispatcher):
        self.storage = storage
        self.state_repo = state_repo
        self.events = event_dispatcher
    
    async def evaluate(self, scope: str, scope_id: str) -> None:
        state = await self.state_repo.get(scope, scope_id)
        if state.summary_in_progress:
            if state.locked_until and now() < state.locked_until:
                return
            # lock expired → cho phép re-trigger
        
        reason = self._check_trigger(state, scope)
        if not reason:
            return
        
        entries = await self.storage.get_entries(scope, scope_id)
        payload = self._build_payload(scope, scope_id, entries, reason)
        
        await self.state_repo.set_in_progress(scope, scope_id, lock_ttl=...)
        self.events.emit(ActiveMemoryEvent.SUMMARY_REQUESTED, scope_id, data=payload)
```

Trigger rule:
- `idle`: `now - last_activity_at ≥ SUMMARY_IDLE_MINUTES` **và** `unsummarized_message_count ≥ SUMMARY_MIN_MESSAGES`.
- `message_count`: `unsummarized_message_count ≥ SUMMARY_MAX_MESSAGES`.
- `token_limit`: `unsummarized_token_count ≥ MAX_WORKING_TOKENS` (user) hoặc `CHANNEL_SUMMARY_TOKEN_LIMIT` (channel).

## Phase 3 — Event flow mới

### 3.1 Event enum

```python
# twin/march7/memories/activate_memory/events/event_dispatcher.py
class ActiveMemoryEvent(str, Enum):
    SUMMARY_REQUESTED = "summary_requested"
    SUMMARY_COMPLETED = "summary_completed"
    SUMMARY_FAILED = "summary_failed"
```

Bỏ `TOKEN_LIMIT_REACHED` (unified flow).

### 3.2 Payload `SUMMARY_REQUESTED`

```json
{
  "scope": "user | channel",
  "scope_id": "...",
  "guild_id": "...",
  "channel_id": "...",
  "reason": "idle | message_count | token_limit",
  "from_entry_id": "...",
  "to_entry_id": "...",
  "from_ts": "...",
  "to_ts": "...",
  "message_count": 42,
  "token_count": 1850,
  "entries": [
    {
      "entry_id": "...",
      "message_id": "...",
      "author_id": "...",
      "author_name": "Flowerf",
      "role": "user | assistant",
      "content": "...",
      "timestamp": "...",
      "reply_to": "..."
    }
  ]
}
```

### 3.3 Payload `SUMMARY_COMPLETED`

```json
{
  "scope": "user | channel",
  "scope_id": "...",
  "summarized_entry_ids": ["...", "..."],
  "page_ids": ["...", "..."],
  "canonical_topic": "Python style",
  "active_participants": ["726...", "user_a"],
  "status": "ok"
}
```

`SUMMARY_FAILED`:
```json
{
  "scope": "...",
  "scope_id": "...",
  "reason": "llm_timeout | llm_error | embed_error | ...",
  "retry_after_seconds": 600
}
```

### 3.4 `MemoryManager` subscribe

```python
# twin/march7/memories/memory_manager.py
self.events.subscribe(ActiveMemoryEvent.SUMMARY_REQUESTED, self._handle_summary_requested)
self.events.subscribe(ActiveMemoryEvent.SUMMARY_COMPLETED, self._handle_summary_completed)
self.events.subscribe(ActiveMemoryEvent.SUMMARY_FAILED, self._handle_summary_failed)

async def _handle_summary_requested(self, event_type, scope_id, payload):
    # Push qua A2A tới Evernight DiscussionConsolidator
    await self._evernight_client.request_consolidation(payload)

async def _handle_summary_completed(self, event_type, scope_id, payload):
    # Cleanup T1
    await self.t1.cleanup_summarized(
        scope=payload["scope"],
        scope_id=payload["scope_id"],
        summarized_entry_ids=payload["summarized_entry_ids"],
        keep_recent=KEEP_RECENT_MESSAGES_AFTER_SUMMARY,
    )
    # Reset state
    await self.state_repo.mark_completed(payload)

async def _handle_summary_failed(self, event_type, scope_id, payload):
    # Clear lock, set retry
    await self.state_repo.mark_failed(payload)
    # KHÔNG xóa raw entries
```

## Phase 4 — Gateway: tách observe/respond + reply-to-bot

### 4.1 `AdminChannels` với mode enum

```python
# gateway/adapters/discord/cogs/admin_channels.py
from enum import Enum

class ChannelMode(str, Enum):
    OBSERVE_ONLY = "observe"
    RESPOND_ALLOWED = "respond"

class AdminChannels(commands.Cog):
    # Storage thay đổi: set[(guild_id, channel_id)] -> dict[(guild_id, channel_id), ChannelMode]
    
    def get_mode(self, guild_id: int, channel_id: int) -> ChannelMode | None:
        return self._allowed_channels.get((guild_id, channel_id))
    
    def is_bot_channel(self, guild_id: int, channel_id: int) -> bool:
        """Backward-compat helper: True nếu channel có bất kỳ mode nào."""
        return (guild_id, channel_id) in self._allowed_channels
```

Admin commands (Discord slash hoặc `!9 admin enable #channel <mode>`):
- `enable #channel observe` — observe-only.
- `enable #channel respond` — respond-allowed (default).
- `disable #channel`.

Migration: config admin channel cũ → tất cả default `RESPOND_ALLOWED` (giữ behavior cũ).

### 4.2 `DiscordMessageConverter` thêm `is_reply_to_bot`

```python
# gateway/adapters/discord/converter.py
is_reply_to_bot = False
if bot_user is not None and message.reference:
    ref = message.reference
    if ref.cached_message:
        is_reply_to_bot = ref.cached_message.author.id == bot_user.id
    elif ref.resolved and hasattr(ref.resolved, "author"):
        is_reply_to_bot = ref.resolved.author.id == bot_user.id

extensions = {
    "is_mentioned": is_mentioned,
    "is_reply_to_bot": is_reply_to_bot,
    "_raw_discord_message": message,
}
```

### 4.3 `UnifiedChannel` thêm `guild_id`

```python
# gateway/shared/model.py
class UnifiedChannel(BaseModel):
    channel_id: str
    platform_name: str
    channel_type: str  # "dm" | "guild" | "thread" | "group"
    name: str | None = None
    guild_id: str | None = None         # NEW — None cho DM
    raw_data: dict | None = None
```

`DiscordChannelConverter.to_unified` set `guild_id` từ `channel.guild.id` (nếu có).

### 4.4 Handler logic mới

```python
# gateway/adapters/discord/handler.py
async def handle_message(self, msg: UnifiedMessage) -> str:
    raw_message = msg.extensions.get("_raw_discord_message")
    is_mentioned = msg.extensions.get("is_mentioned", False)
    is_reply_to_bot = msg.extensions.get("is_reply_to_bot", False)
    is_dm = msg.channel.channel_type == "dm"
    
    mode = None
    if raw_message.guild:
        admin_cog = self._get_bot().get_cog("AdminChannels")
        if admin_cog:
            mode = admin_cog.get_mode(raw_message.guild.id, raw_message.channel.id)
    
    is_observe_channel = mode is not None
    is_respond_channel = mode == ChannelMode.RESPOND_ALLOWED
    
    should_observe = is_dm or is_mentioned or is_reply_to_bot or is_observe_channel
    should_respond = is_dm or is_mentioned or is_reply_to_bot or is_respond_channel
    
    if not should_observe:
        return ""
    
    # Route observe
    if is_dm or (not raw_message.guild):
        await self._memory_manager.observe_user_message(
            user_id=msg.user.platform_id,
            role="user",
            content=msg.content,
        )
    else:
        await self._memory_manager.observe_channel_message(
            guild_id=str(raw_message.guild.id),
            channel_id=str(raw_message.channel.id),
            author_id=msg.user.platform_id,
            author_name=msg.user.display_name,
            message_id=msg.message_id,
            content=msg.content,
            reply_to=msg.reply_to,
        )
    
    if not should_respond:
        return ""
    
    # ... continue routing tới agent (giống cũ) ...
```

## Phase 5 — T2: mở rộng schema + DiscussionConsolidator

### 5.1 `T2Page` thêm field

```python
# twin/shared/memories/t2/models.py
class T2Page(BaseModel):
    # ... 29 field cũ giữ nguyên ...
    
    participants: list[str] = Field(default_factory=list)
    source_refs: list[dict] = Field(default_factory=list)
    # source_refs example:
    # [{"channel_id": "1234", "guild_id": "...", "msg_from": "1001", "msg_to": "1048", "from_ts": "...", "to_ts": "..."}]
```

`user_id` field **giữ nguyên semantic** — chứa real Discord user_id (digit). Channel chỉ là metadata.

### 5.2 FT index update

```python
# twin/shared/memories/t2/store.py — _create_index
# Thêm vào SCHEMA của PAGE_INDEX:
"$.participants[*]", "AS", "participants", "TAG",
```

**Migration**: FT.CREATE skip nếu đã exist (`store.py:74-79`). Deploy cần:
1. `FT.DROPINDEX idx:t2:page` (không xóa data, chỉ drop index)
2. Restart service → `_create_index` chạy lại với schema mới
3. Hoặc viết script migration riêng (recommended cho production).

### 5.3 `DiscussionConsolidator` (Evernight)

```python
# twin/shared/memories/discussion_consolidator.py — module mới
class DiscussionConsolidator:
    def __init__(self, llm, t2_memory, state_repo, event_dispatcher):
        ...
    
    async def consolidate(self, payload: dict) -> None:
        try:
            transcript = self._format_transcript(payload)
            mode = "multi_user" if payload["scope"] == "channel" else "single_user"
            
            summary = await self._llm_summarize(transcript, mode)
            # summary = {
            #   "canonical_topic": "...",
            #   "category": "...",
            #   "current_summary": "...",
            #   "key_points": [...],
            #   "participants": [...],
            #   "active_participants": [...],
            #   "importance": 1-5,
            #   "confidence": 0-1,
            # }
            
            if summary.get("status") == "skipped":
                # LLM judge nội dung rác, không lưu T2
                await self._emit_completed(payload, page_ids=[], status="skipped")
                return
            
            page_ids = []
            for participant_id in summary["active_participants"]:
                page = self._build_page(participant_id, summary, payload)
                existing = await self.t2.lookup_by_page_id(page.page_id)
                merged = self._merge(existing, page) if existing else page
                await self.t2.embed_page(merged)
                page_ids.append(page.page_id)
            
            await self._emit_completed(payload, page_ids=page_ids, status="ok")
        
        except Exception as e:
            await self._emit_failed(payload, reason=str(e))
    
    def _build_page(self, participant_id: str, summary: dict, payload: dict) -> T2Page:
        canonical_topic = summary["canonical_topic"]
        page_id = generate_topic_id(participant_id, canonical_topic)
        
        source_ref = {
            "channel_id": payload.get("channel_id"),
            "guild_id": payload.get("guild_id"),
            "msg_from": payload["from_entry_id"],
            "msg_to": payload["to_entry_id"],
            "from_ts": payload["from_ts"],
            "to_ts": payload["to_ts"],
        }
        
        return T2Page(
            page_id=page_id,
            user_id=participant_id,
            scope="user_global",
            topic_id=page_id,
            canonical_topic=canonical_topic,
            category=summary.get("category", "casual"),
            current_summary=summary["current_summary"],
            key_points=summary["key_points"],
            participants=summary["participants"],
            source_refs=[source_ref],
            importance=summary.get("importance", 3),
            confidence=summary.get("confidence", 1.0),
        )
    
    def _merge(self, existing: T2Page, new: T2Page) -> T2Page:
        # current_summary: LLM merge (delegate sang sub-call) hoặc append history
        # key_points: dedupe + concat
        # participants: union
        # source_refs: append
        # access_count: existing.access_count + 1
        # last_updated: now
        ...
```

### 5.4 Prompt LLM (multi-user mode)

```text
Bạn là memory consolidator cho Bé Bảy.

Input là transcript của một đoạn hội thoại. Mode: {single_user | multi_user}.

Hãy tạo một episodic wiki memory. Không lưu mọi câu chat. Chỉ lưu:
- quyết định kỹ thuật
- facts quan trọng
- preference của user
- context dự án
- vấn đề đã debug
- kết luận đã thống nhất

Bỏ qua:
- xã giao
- câu ngắn không có ngữ cảnh
- joke không liên quan
- spam

Output JSON:
{
  "canonical_topic": "...",
  "category": "...",
  "current_summary": "...",
  "key_points": [...],
  "participants": [...],                       // ai có mặt trong transcript
  "active_participants": [...],                // ai contribute substantive (>= 1 turn có ý nghĩa)
  "importance": 1-5,
  "confidence": 0-1,
  "status": "ok" | "skipped"                   // skipped nếu nội dung không đáng lưu
}
```

`active_participants` quyết định fan-out. LLM tự đánh giá. Khi `single_user` mode: `active_participants` luôn = `[user_id]`.

## Phase 6 — T1 cleanup sau `SUMMARY_COMPLETED`

```python
# twin/march7/memories/activate_memory/activate_memory_service.py
async def cleanup_summarized(
    self,
    scope: str,
    scope_id: str,
    summarized_entry_ids: List[str],
    keep_recent: int = 3,
) -> None:
    """Cleanup raw entries sau khi T2 báo SUMMARY_COMPLETED."""
    entries = await self.storage.get_entries(scope, scope_id)
    entries.sort(key=lambda e: e.timestamp)
    
    recent_ids = {e.entry_id for e in entries[-keep_recent:]}
    ids_to_delete = [
        eid for eid in summarized_entry_ids
        if eid not in recent_ids
    ]
    
    if ids_to_delete:
        await self.storage.delete_entries(scope, scope_id, ids_to_delete)
```

`SummaryFailed` handler:
```python
async def _handle_summary_failed(self, event_type, scope_id, payload):
    await self.state_repo.clear_in_progress(payload["scope"], payload["scope_id"])
    await self.state_repo.set_locked_until(
        payload["scope"], payload["scope_id"],
        until=now() + timedelta(seconds=payload.get("retry_after_seconds", 600))
    )
    # KHÔNG xóa raw — giữ cho retry
```

## Phase 7 — Channel context cho prompt

Khi bot được mention trong channel, prompt nên có channel context (3-15 message gần nhất từ T1 channel scope):

```text
[Recent channel context]
Flowerf: ...
User A: ...
User B: ...

[Current request]
Flowerf: vậy chốt sao?
```

### 7.1 `build_channel_context`

```python
# twin/march7/memories/channel_context.py — hiện file rỗng (1 dòng), implement:
def build_channel_context(
    entries: List[MemoryEntry],
    max_entries: int = 12,
    max_tokens: int = 1500,
) -> str:
    """Format channel entries thành readable transcript với author_name."""
    if not entries:
        return ""
    
    sorted_entries = sorted(entries, key=lambda e: e.timestamp)
    selected = []
    total = 0
    for entry in reversed(sorted_entries):
        if len(selected) >= max_entries:
            break
        if selected and total + entry.tokens > max_tokens:
            break
        selected.append(entry)
        total += entry.tokens
    selected.reverse()
    
    lines = []
    for e in selected:
        name = e.author_name or e.user_id
        lines.append(f"{name}: {e.content}")
    return "\n".join(lines)
```

### 7.2 `MemoryManager.get_context`

Mở rộng để include channel context khi message đến từ channel scope:

```python
async def get_context(
    self, user_id: str, current_query: str, channel_id: str | None = None
) -> Tuple[str, List[Dict], str | None]:
    """Returns (system_prompt, user_context_messages, channel_context_text)."""
    ...
    channel_context = None
    if channel_id:
        channel_entries = await self.t1.storage.get_entries("channel", channel_id)
        channel_context = build_channel_context(channel_entries)
    
    return system_prompt, context_messages, channel_context
```

Bộ Agent inject `channel_context` vào system prompt khi có.

## Phase 8 — Multi-channel polling cho idle trigger

Sử dụng lại `InactivityTrigger` của Evernight (`twin/evernight/triggers/inactivity_trigger.py`), mở rộng để scan cả channel scope:

```python
# twin/evernight/triggers/inactivity_trigger.py
async def scan(self):
    # Scan user scope (đã có)
    for scope_id in await self.state_repo.list_active("user"):
        await self._check_and_trigger("user", scope_id)
    
    # Scan channel scope (mới)
    for scope_id in await self.state_repo.list_active("channel"):
        await self._check_and_trigger("channel", scope_id)
```

`state_repo.list_active(scope)`: trả các `scope_id` có `unsummarized_message_count > 0` và `summary_in_progress == False`.

## Files cần sửa / thêm

### T1 (March7)
- ✏️ `twin/march7/memories/activate_memory/models.py` — extend `MemoryEntry`, thêm `SummaryState`.
- ✏️ `twin/march7/memories/activate_memory/constants.py` — thêm `SUMMARY_*`, `CHANNEL_SUMMARY_TOKEN_LIMIT`, `KEEP_RECENT_MESSAGES_AFTER_SUMMARY`.
- ✏️ `twin/march7/memories/activate_memory/events/event_dispatcher.py` — thay enum, bỏ `TOKEN_LIMIT_REACHED`, thêm 3 event mới.
- ✏️ `twin/march7/memories/activate_memory/activate_memory_service.py` — `observe_user_message`, `observe_channel_message`, `cleanup_summarized`.
- ➕ `twin/march7/memories/activate_memory/management/summary_policy.py` — module mới.
- ➕ `twin/march7/memories/activate_memory/management/state_repository.py` — module mới (SummaryState CRUD trong Redis).
- ✏️ `twin/march7/memories/activate_memory/management/context_builder.py` — không sửa user path, thêm wrapper nếu cần.
- ✏️ `twin/march7/memories/activate_memory/storage/base_storage.py` — scope param API.
- ✏️ `twin/march7/memories/activate_memory/storage/redis_storage.py` — implement scope key.
- ✏️ `twin/march7/memories/activate_memory/storage/redis_stack_storage.py` — implement scope key.
- ✏️ `twin/march7/memories/activate_memory/storage/ram_storage.py` — implement scope key.
- ✏️ `twin/march7/memories/memory_manager.py` — subscribe 3 event mới, route qua A2A tới Evernight.
- ✏️ `twin/march7/memories/channel_context.py` — implement `build_channel_context` (hiện rỗng).

### Gateway
- ✏️ `gateway/adapters/discord/cogs/admin_channels.py` — `ChannelMode` enum, `get_mode()`.
- ✏️ `gateway/adapters/discord/handler.py` — tách `should_observe`/`should_respond`, route observe theo scope.
- ✏️ `gateway/adapters/discord/converter.py` — `is_reply_to_bot`, `guild_id` cho `UnifiedChannel`.
- ✏️ `gateway/shared/model.py` — `UnifiedChannel.guild_id`.

### T2 (Shared / Evernight)
- ✏️ `twin/shared/memories/t2/models.py` — `T2Page` thêm `participants`, `source_refs`.
- ✏️ `twin/shared/memories/t2/store.py` — FT.CREATE thêm `participants[*] TAG`.
- ➕ `twin/shared/memories/discussion_consolidator.py` — module mới.
- ✏️ `twin/evernight/consolidation_runner.py` — wire `DiscussionConsolidator` vào A2A subscribe.
- ✏️ `twin/evernight/triggers/inactivity_trigger.py` — scan thêm channel scope.

### Tests
- ➕ `tests/unit/summary_policy_test.py`
- ➕ `tests/unit/discussion_consolidator_test.py`
- ➕ `tests/unit/t1_channel_observe_test.py`
- ✏️ `tests/unit/inactivity_trigger_test.py` — extend cho channel scope.
- ✏️ `tests/unit/consolidation_runner_test.py` — wire mới.
- ✏️ `tests/unit/t1_context_builder_test.py` — extend cho channel.
- ✏️ `tests/gateway/test_gateway.py` — admin channels mode, reply-to-bot.
- ➕ `tests/integration/channel_summary_flow_test.py` — end-to-end.

## Thứ tự triển khai an toàn

1. **Phase 1.1 + 1.2**: Mở rộng `MemoryEntry` + scope-aware storage. Test: save user entry / channel entry, lấy ra đúng scope.
2. **Phase 4 (Gateway)**: Tách observe/respond + `is_reply_to_bot` + `AdminChannels` mode. Test: channel observe-only thì không reply, channel respond thì reply như cũ.
3. **Phase 7 (Channel context)**: Bot được mention trong channel có thể lấy được recent channel context. Test: User A và B chat, Flowerf mention bot "vậy chốt sao?", bot hiểu "vậy" = đoạn trước.
4. **Phase 1.3 + 2 (SummaryState + SummaryPolicy)**: Thêm state + policy nhưng chưa gọi T2 thật. Test: 30 msg + idle → policy emit `SUMMARY_REQUESTED`.
5. **Phase 3 (Event flow)**: Thay enum, March7 emit qua A2A. Mock Evernight side để test event được nhận.
6. **Phase 5 (T2 + DiscussionConsolidator mock)**: Schema + index migration trước. DiscussionConsolidator ban đầu log payload thay vì gọi LLM thật.
7. **Phase 5 (LLM thật + fan-out)**: Bật LLM. Test: discussion window → summary JSON → N page (per active_participant) → `embed_page()`.
8. **Phase 6 (Cleanup)**: T1 cleanup sau `SUMMARY_COMPLETED`. Test: summary OK → raw cũ bị xóa, raw mới giữ. Summary fail → raw nguyên.
9. **Phase 8 (Polling)**: Mở rộng `InactivityTrigger`. Test: nhiều channel idle cùng lúc đều trigger.

## Test cases bắt buộc

- T1 channel scope key format: `active_memory:channel:{channel_id}`.
- Observe channel KHÔNG trigger reply nếu mode `OBSERVE_ONLY` và không mention/reply-to-bot.
- Mention bot trong channel mode `OBSERVE_ONLY` → vẫn reply (observe + respond).
- Reply-to-bot trong channel `OBSERVE_ONLY` → bot reply (theo decision Gap #3).
- 30 message + idle 30 phút → `SUMMARY_REQUESTED(reason="idle")`.
- 60 message → `SUMMARY_REQUESTED(reason="message_count")` (không cần idle).
- Token ≥ threshold → `SUMMARY_REQUESTED(reason="token_limit")`.
- DiscussionConsolidator nhận channel payload, fan-out `len(active_participants)` page.
- DiscussionConsolidator nhận user 1-1 payload, fan-out 1 page (đúng user_id).
- Page `merge` khi `(participant_id, canonical_topic)` đã tồn tại — `key_points` dedup, `source_refs` append.
- `SUMMARY_COMPLETED` → T1 xóa raw, giữ 3 message cuối, reset counter.
- `SUMMARY_FAILED` → T1 không xóa raw, set `locked_until`.
- `summary_in_progress=true` + `locked_until > now` → policy skip không emit lại.
- FT search `@participants:{user_a}` trả về page có user_a trong participants.

## Bổ sung / lưu ý

- Privacy multi-user: nếu channel có guest người lạ, page fan-out cho họ sẽ chứa nội dung từ user khác. Cho usage hiện tại (Bé Bảy của Flowerf + người tin cậy) chấp nhận được. Future: thêm flag `private` ở channel-level để skip fan-out cho non-owner.
- `T2Page.user_id` cho channel fan-out vẫn là **real user_id** (digit). KHÔNG dùng sentinel `"channel:..."`. Field `source_refs` chứa channel info để traceback.
- `SearchMemoryTool` không phải sửa: vì user-centric, search per-user vẫn hoạt động đúng. Nếu sau này muốn filter "page X trong channel Y", thêm field `scope_filter` hoặc `channel_filter` cho tool — defer tới phase sau.
- `RedisStackStorage` adapter T1 hiện chỉ phục vụ raw entries. `SummaryState` dùng pure Redis Hash (`HSET`/`HGETALL`), không qua adapter — giữ tách biệt schema.
- Embedding cost: với fan-out, embedding nên tính 1 lần cho `(canonical_topic, current_summary, key_points)` rồi share giữa N page. `T2Embedder.embed_page` hiện tính per-page; có thể optimize sau khi đo cost thực tế.
- `_create_index` skip nếu index đã tồn tại → khi thêm `participants` field cần DROP/CREATE lại index. Viết migration script đi kèm deploy.
- Backward compat: data T2 cũ không có `participants`/`source_refs` → Pydantic auto default `[]`. FT search vẫn hoạt động cho data cũ.
- Test integration cần Redis Stack lên (`docker compose up redis`).

## Kết luận thiết kế

```text
T1: observe (user + channel) → SummaryPolicy → SUMMARY_REQUESTED
T2: DiscussionConsolidator (Evernight) → LLM → fan-out per active_participant → embed_page
T1: cleanup raw sau khi nhận SUMMARY_COMPLETED, giữ recent
```

Tinh thần: **bot nhớ theo user, kênh chỉ là metadata**. Cho phép bot follow user qua channel/DM một cách tự nhiên, không bị fragment memory theo nơi xảy ra.
