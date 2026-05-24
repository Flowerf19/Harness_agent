# Channel Discussion Memory Plan

## Muc tieu

Cai tien memory de bot hieu duoc cuoc tro chuyen nhieu user trong channel, nhung khong doi loi T2.

Kien truc muc tieu:

```text
Discord channel messages
  -> T1 Channel Active Memory
  -> SummaryPolicy detects idle/count/token threshold
  -> SUMMARY_REQUESTED event
  -> T2 DiscussionConsolidator
  -> WikiPagePayload / existing page merge
  -> EpisodicMemoryManager.embed_page()
  -> existing T2 storage/search
  -> SUMMARY_COMPLETED event
  -> T1 cleanup summarized window
```

T2 hien dang la facade cho Wiki/Episodic page, co `search()`, `search_pages()`, `embed_page()`, `lookup_by_page_id()`, `refresh_access()`. Giu nguyen phan nay. `embed_page()` da build embedding tu `canonical_topic + current_summary + key_points` roi upsert vao storage, nen chi can feed page dung schema.

## Loi va diem de quen

- Khong observe toan server. Chi observe DM, allowed bot channel, thread/channel da bat bot, va message reply bot neu can.
- Bot duoc nghe channel duoc phep, nhung khong reply neu khong duoc goi bang DM/mention/tag/prefix/allowed bot flow.
- Token limit khong nen cleanup truc tiep nua; chuyen thanh `SUMMARY_REQUESTED`.
- T1 khong xoa raw entries khi vua phat event. Chi cleanup sau `SUMMARY_COMPLETED`.
- Summary fail khong duoc lam mat memory. Clear lock, set retry/locked_until, giu raw entries.
- T1 khong nen biet qua nhieu chi tiet schema T2. Duong tich hop nen la `DiscussionConsolidator -> WikiPagePayload -> EpisodicMemoryManager.embed_page()`.
- T2 prompt phai la multi-user discussion, khong phai "user noi voi bot".

## Phase 1 - Mo rong T1 cho channel memory

### 1.1 Them memory scope

Them scope moi, khong bo user memory cu:

```text
active_memory:user:{user_id}
active_memory:channel:{channel_id}
```

### 1.2 Mo rong MemoryEntry

Can metadata de T2 biet ai ban luan gi, nhung khong can luu raw forever:

```python
class MemoryEntry(BaseModel):
    scope: str                 # "user" | "channel"
    scope_id: str              # user_id hoac channel_id

    user_id: str               # nguoi gui
    author_id: str
    author_name: str

    guild_id: str | None
    channel_id: str | None
    message_id: str | None
    reply_to: str | None

    role: str                  # "user" | "assistant" | "system"
    content: str
    tokens: int
    timestamp: datetime
    entry_id: str
```

### 1.3 Them API observe ambient message

Khong dung `add_message()` cu cho tat ca. Them method rieng:

```python
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
    ...
```

Nhiem vu:

- luu message vao `active_memory:channel:{channel_id}`
- dem token
- cap nhat `SummaryState`
- khong goi LLM
- khong reply

## Phase 2 - Sua gateway filter: nghe nhieu hon, tra loi nhu cu

Hien handler filter theo DM / mention / allowed channel roi moi route vao agent. Can tach observe va respond:

```python
should_observe = is_allowed_channel or is_dm or is_mentioned
should_respond = is_dm or is_mentioned or is_allowed_bot_channel

if should_observe:
    await memory_manager.observe_channel_message(...)

if not should_respond:
    return ""

response = await self._a2a_client.send_chat_task(...)
```

Bot nghe cuoc tro chuyen trong channel duoc phep, nhung khong tra loi neu khong duoc goi.

## Phase 3 - Them SummaryState theo channel

Can state de biet doan nao da tom tat, doan nao chua:

```python
class SummaryState(BaseModel):
    scope: str                  # "channel"
    scope_id: str               # channel_id

    last_activity_at: datetime
    last_summarized_at: datetime | None
    last_summarized_entry_id: str | None

    unsummarized_message_count: int
    unsummarized_token_count: int

    summary_in_progress: bool
    locked_until: datetime | None
```

Redis key:

```text
summary_state:channel:{channel_id}
```

Neu T1 dang dung Redis Stack container thi van dung Redis Hash binh thuong, khong can Redis rieng.

## Phase 4 - Logic tao event tom tat

Event chay khi channel ngung noi chuyen khoang 30 phut va du luot hoi thoai, hoac khi vuot nguong message/token.

Config de xuat:

```python
SUMMARY_IDLE_MINUTES = 30
SUMMARY_MIN_MESSAGES = 30
SUMMARY_MAX_MESSAGES = 60
SUMMARY_TOKEN_LIMIT = 2000
```

Co the tan dung `SESSION_TIMEOUT_MINUTES = 30` va `MAX_WORKING_TOKENS = 2000` hien co.

Trigger:

- Idle: `idle >= 30 phut` va `unsummarized_message_count >= 30` va `summary_in_progress == false` -> `SUMMARY_REQUESTED(reason="idle")`
- Message count: `unsummarized_message_count >= 60` va `summary_in_progress == false` -> `SUMMARY_REQUESTED(reason="message_count")`
- Token limit: `unsummarized_token_count >= 2000` va `summary_in_progress == false` -> `SUMMARY_REQUESTED(reason="token_limit")`

Event enum:

```python
class ActiveMemoryEvent(str, Enum):
    TOKEN_LIMIT_REACHED = "token_limit_reached"      # giu de tuong thich
    SUMMARY_REQUESTED = "summary_requested"
    SUMMARY_COMPLETED = "summary_completed"
    SUMMARY_FAILED = "summary_failed"
```

Payload gui sang T2:

```json
{
  "scope": "channel",
  "scope_id": "channel_id",
  "guild_id": "guild_id",
  "channel_id": "channel_id",
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
      "content": "...",
      "timestamp": "...",
      "reply_to": "..."
    }
  ]
}
```

## Phase 5 - T2 tich hop DiscussionConsolidator

Khong sua `EpisodicMemoryManager` nhieu. Them service dung truoc no:

```text
DiscussionConsolidator
  -> EpisodicMemoryManager
```

`DiscussionConsolidator` nhan event tu T1 va lam:

1. Nhan raw entries tu T1.
2. Format thanh transcript nhieu user.
3. Goi LLM tom tat.
4. Extract `canonical_topic`, `current_summary`, `key_points`, `category`, `importance`, `participants`, `decisions`, `source refs`.
5. Lookup page cu theo topic/page_id neu co.
6. Merge voi page cu.
7. Goi `EpisodicMemoryManager.embed_page(page)`.
8. Emit `SUMMARY_COMPLETED` hoac `SUMMARY_FAILED`.

T2 output van la `WikiPagePayload`:

- `canonical_topic`
- `current_summary`
- `key_points`
- `category`
- `importance`
- `user_id`
- `created_at`
- `last_updated`
- `last_accessed`
- `embedding`

Neu can participants/source, cach it pha nhat la nhet gon vao `key_points`:

- `Participants: Flowerf, user_A, user_B`
- `Source: Discord channel 123, messages 1001-1048`

Cach sach hon la them optional metadata neu schema cho phep:

```python
participants: list[str] = []
source_refs: list[dict] = []
```

De giu logic T2 toi da, uu tien cach 1 truoc.

Prompt tom tat phai la multi-user discussion:

```text
Ban la memory consolidator cho Discord channel.

Input la transcript nhieu user. Hay tao mot episodic wiki memory.
Khong luu moi cau chat. Chi luu:
- quyet dinh ky thuat
- facts quan trong
- preference cua user
- context du an
- van de da debug
- ket luan da thong nhat

Bo qua:
- xa giao
- cau ngan khong co ngu canh
- joke khong lien quan
- spam

Output JSON:
{
  "canonical_topic": "...",
  "category": "...",
  "current_summary": "...",
  "key_points": [...],
  "participants": [...],
  "importance": 1-5,
  "confidence": 0-1
}
```

Merge logic:

- Neu `canonical_topic` giong page cu -> merge/update page cu.
- Neu topic moi ro rang -> tao page moi.
- Neu noi dung rac/khong du gia tri -> tra status `skipped`.

```python
page = await consolidator.to_wiki_page(summary_result)
existing = await episodic.lookup_by_page_id(page.page_id)

if existing:
    merged = await wiki_merge.merge(existing, page)
else:
    merged = page

ok = await episodic.embed_page(merged)
```

## Phase 6 - Cleanup sau SUMMARY_COMPLETED

T1 chi xoa raw sau khi T2 bao thanh cong.

`SUMMARY_COMPLETED` payload:

```json
{
  "scope": "channel",
  "scope_id": "channel_id",
  "summarized_entry_ids": ["..."],
  "page_id": "...",
  "canonical_topic": "...",
  "status": "ok"
}
```

T1 lam:

- mark `last_summarized_entry_id`
- reset `unsummarized_message_count/token_count`
- clear `summary_in_progress`
- delete summarized entries cu
- giu lai 3-10 message moi nhat de khong dut ngu canh

Khi `SUMMARY_FAILED`:

- clear `summary_in_progress`
- khong xoa entries
- set retry_after / locked_until
- neu token qua cao thi cleanup nhe, nhung bao ve recent messages

## Phase 7 - Channel context khi bot duoc goi

Khi bot duoc mention, prompt nen co them channel context:

```text
[Recent channel context]
Flowerf: ...
User A: ...
User B: ...

[Current request]
Flowerf: ...
```

Khong can lay T2 moi lan. T2 chi dung khi agent chu dong search memory hoac can long-term memory.

`ContextBuilder` hien chi lay N entry gan nhat va bo metadata. Can them builder rieng:

```python
build_channel_context(entries, max_entries=12)
```

Output phai co `author_name`, neu khong LLM khong hieu ai noi gi.

## Phase 8 - File/module can them hoac sua

T1:

- `twin/march7/memories/activate_memory/models.py`: mo rong `MemoryEntry`
- `twin/march7/memories/activate_memory/constants.py`: them `SUMMARY_IDLE_MINUTES`, `SUMMARY_MIN_MESSAGES`, `SUMMARY_MAX_MESSAGES`
- `twin/march7/memories/activate_memory/events/event_dispatcher.py`: them `SUMMARY_REQUESTED`, `SUMMARY_COMPLETED`, `SUMMARY_FAILED`
- `twin/march7/memories/activate_memory/activate_memory_service.py`: them `observe_channel_message()`, `evaluate_summary_policy()`
- `twin/march7/memories/activate_memory/management/summary_policy.py`: module moi
- `twin/march7/memories/activate_memory/management/context_builder.py`: them `build_channel_context()`
- `twin/march7/memories/activate_memory/storage/redis_storage.py`: ho tro scope key khong chi `user_id`, luu `SummaryState`

Gateway:

- `gateway/adapters/discord/handler.py`: tach observe/respond, goi `observe_channel_message()` truoc khi filter return
- `gateway/adapters/discord/converter.py`: bao dam co `author_name`, `channel_id`, `guild_id`, `reply_to`

Memory manager:

- `twin/march7/memories/memory_manager.py`: subscribe `SUMMARY_REQUESTED`, inject `discussion_consolidator` hoac T2 service, handle `SUMMARY_COMPLETED` / `SUMMARY_FAILED`

T2:

- `twin/shared/memories/discussion_consolidator.py`: module moi
- `twin/shared/memories/episodic_memory_manager.py`: giu nguyen search/embed, optional them `consolidate_discussion(data)`

## Thu tu trien khai an toan

1. Them channel memory observe nhung chua summary, chua T2.
   - Test: message trong channel duoc luu vao Redis key `active_memory:channel:{channel_id}`.
   - Test: bot khong reply neu khong mention.
2. Khi mention bot, bot lay duoc recent channel context.
   - Test: User A va B noi chuyen, Flowerf mention bot "vay chot sao?", bot hieu "vay" la doan truoc.
3. Them `SummaryState` + `SummaryPolicy`.
   - Test: 30 message + idle 30 phut -> `SUMMARY_REQUESTED`.
   - Test: 60 message -> `SUMMARY_REQUESTED`.
   - Test: token >= 2000 -> `SUMMARY_REQUESTED`.
4. Them `DiscussionConsolidator` mock, ban dau khong goi LLM that, chi log payload/window.
5. Cho T2 summarize that va tao `WikiPagePayload`.
   - Test: discussion window -> summary JSON -> page -> `embed_page()`.
6. Them cleanup sau `SUMMARY_COMPLETED`.
   - Test: summary OK -> raw cu duoc xoa.
   - Test: summary fail -> raw con nguyen.

## Ket luan thiet ke

Plan dung:

```text
T1: nghe + luu + phat event
T2: tom tat + merge + embed/upsert
T1: cleanup sau khi T2 bao thanh cong
```

Phan can tich hop voi T2 chi la `DiscussionConsolidator -> WikiPagePayload -> EpisodicMemoryManager.embed_page()`. Khong de T1 biet chi tiet schema T2 qua nhieu, va khong sua sau search/upsert hien tai.
