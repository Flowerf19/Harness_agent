# Phase 2: Group Chat Context

## Goal
Enable group chat context by changing session key from `user_id` to `channel_id/thread_id`.

**Depends on:** Phase 1 (Alias Index)

---

## Architecture Changes

### Current
```
Storage Key: active_memory:{user_id}
Message: {"role": "user", "content": "message"}
Context: sender's T1 + sender's T3
```

### New
```
Storage Key: active_memory:{channel_id} or active_memory:{thread_id}
Message: {"role": "user", "content": "[DisplayName]: message"}
Context: channel's T1 + ALL participants' T3
```

---

## Implementation

### 2.1 Storage Key Refactoring

**Files:** `src/services/memories/activate_memory/`

**Changes:**
- `activate_memory_service.py`: Accept `channel_id` instead of `user_id`
- `redis_storage.py`: Key pattern `active_memory:{channel_id}`
- `ram_storage.py`: Same key pattern

```python
# Before
async def add_message(self, user_id: str, role: str, content: str)

# After
async def add_message(self, channel_id: str, role: str, content: str, user_id: str | None = None)
```

---

### 2.2 ChannelContext Class

**Location:** `src/services/memories/channel_context.py` (NEW)

```python
class ChannelContext:
    def __init__(self):
        self._participants: dict[str, set[str]] = {}  # channel_id -> user_ids
        self._max_participants = 10  # Token limit
    
    def add_participant(self, channel_id: str, user_id: str):
        if channel_id not in self._participants:
            self._participants[channel_id] = set()
        self._participants[channel_id].add(user_id)
        # Trim if exceeds max
        if len(self._participants[channel_id]) > self._max_participants:
            # Remove oldest participants (implementation needed)
            pass
    
    def get_participants(self, channel_id: str) -> list[str]:
        return list(self._participants.get(channel_id, []))
```

---

### 2.3 Message Formatting

**Location:** `src/services/chat_coordinator.py` (MODIFY)

```python
# For group channels, add attribution
if message.guild:  # Group channel
    display_name = message.author.display_name
    formatted_content = f"[{display_name}]: {content}"
else:  # DM
    formatted_content = content  # No prefix or use username

await memory_manager.add_message(
    channel_id=str(message.channel.id),
    role="user",
    content=formatted_content,
    user_id=str(message.author.id)
)
```

---

### 2.4 Server Directory Injection

**Location:** `src/services/memories/memory_manager.py` (MODIFY)

```python
async def get_context(self, channel_id: str, server_id: str | None):
    # Get channel's T1 messages
    t1_messages = await self.t1.get_messages(channel_id)
    
    # Get participants' T3 profiles
    participants = self.channel_context.get_participants(channel_id)
    t3_profiles = await asyncio.gather(
        *[self.t3.get_system_prompt_context(uid) for uid in participants]
    )
    
    # Inject server directory
    if server_id:
        directory = await self.alias_manager.get_server_directory(server_id)
        directory_context = self._format_directory(directory)
    
    return system_prompt, t1_messages, t3_profiles, directory_context
```

---

### 2.5 Coordinator Changes

**Location:** `src/services/chat_coordinator.py` (MODIFY)

```python
async def process_message(
    self,
    channel_id: str,      # Changed from user_id
    server_id: str | None,
    user_id: str,
    content: str
):
    # Track participant
    self.channel_context.add_participant(channel_id, user_id)
    
    # Get full context
    context = await self.memory_manager.get_context(channel_id, server_id)
    
    # Generate response
    response = await self.llm.generate(context)
```

---

### 2.6 Gateway Changes

**Location:** `src/cogs/chat_gateway.py` (MODIFY)

```python
bot_response = await coordinator.process_message(
    channel_id=str(message.channel.id),
    server_id=str(message.guild.id) if message.guild else None,
    user_id=str(message.author.id),
    content=content
)
```

---

## Tasks

| ID | Task | Status |
|----|------|--------|
| 2.1 | Refactor T1 storage key to channel_id | ✅ Completed |
| 2.2 | Create `ChannelContext` class | ✅ Completed |
| 2.3 | Add message attribution formatting | ✅ Completed |
| 2.4 | Implement server directory injection | ✅ Completed |
| 2.5 | Update `chat_coordinator.py` signature | ✅ Completed |
| 2.6 | Update `chat_gateway.py` to pass channel_id | ✅ Completed |
| 2.7 | Update `memory_manager.py` for multi-T3 | ✅ Completed |
| 2.8 | TTL cleanup for inactive channels | ✅ Completed |
| 2.9 | Unit tests for ChannelContext | ✅ Completed |

---

## Constraints

- **DM unchanged:** DM channels have channel_id too, works uniformly
- **Token limit:** Max 10 participants' T3 profiles
- **TTL:** Inactive channels cleaned after 24h

---

## Testing

### Scenarios
1. Group channel → messages stored under channel_id
2. DM → works unchanged (channel_id is DM channel)
3. Thread → uses thread_id as key
4. Participant limit → max 10 profiles loaded
5. Cross-user T3 → Bot knows all participants