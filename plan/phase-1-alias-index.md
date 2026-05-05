# Phase 1: Alias Index (Danh bạ Định danh)

## Goal
Zero-latency user identity directory tracking aliases across Discord servers.

---

## Storage: `memories/INDEX.md`

### Structure
```markdown
# Server Directory

## DXTech_Group (Server ID: 123456789)
| User ID | Display Name | Aliases |
|---------|--------------|---------|
| 418621389449199616 | Hòa | [Hòa, Hòa IT, Admin] |
| 789xxx | Quang | [Quang, Quang STAR] |

## Personal_Server (Server ID: 987654321)
| User ID | Display Name | Aliases |
|---------|--------------|---------|
| 418xxx | Hòa | [Hòa] |
```

### Parsing Strategy
- Regex-based table parsing (no heavy library)
- Unicode support (Vietnamese names)
- Append-only for performance

---

## Implementation

### 1.1 Storage Layer: `alias_storage.py`

**Location:** `src/services/memories/alias_storage.py` (NEW)

**Methods:**
```python
class AliasStorage:
    async def track_alias(server_id: str, user_id: str, display_name: str)
    async def resolve_alias(server_id: str, name: str) -> str | None
    async def get_server_directory(server_id: str) -> list[dict]
    async def get_all_aliases(user_id: str) -> list[str]
```

**Concurrency:** `asyncio.Lock` per server_id

---

### 1.2 Service Layer: `alias_manager.py`

**Location:** `src/services/memories/alias_manager.py` (NEW)

**Pattern:** Cache-first with storage fallback

```python
class AliasManager:
    def __init__(self, storage: AliasStorage):
        self._cache: dict[str, dict] = {}  # server_id -> directory
        self._storage = storage
    
    async def track_alias(self, server_id, user_id, display_name):
        # Fire-and-forget to storage
        asyncio.create_task(self._storage.track_alias(...))
        # Update cache immediately
        self._update_cache(server_id, user_id, display_name)
    
    async def resolve_alias(self, server_id, name) -> str | None:
        # Check cache first
        if server_id in self._cache:
            for user in self._cache[server_id]["members"]:
                if name in user["aliases"]:
                    return user["user_id"]
        # Fallback to storage
        return await self._storage.resolve_alias(server_id, name)
```

---

### 1.3 Integration

#### `dependencies.py` (MODIFY)

```python
# Add AliasManager to AppContainer
self.alias_storage = AliasStorage()
self.alias_manager = AliasManager(self.alias_storage)
```

#### `chat_gateway.py` (MODIFY)

```python
@commands.Cog.listener()
async def on_message(self, message: discord.Message):
    # ... existing filters ...
    
    # Extract identity info
    server_id = str(message.guild.id) if message.guild else "dm"
    user_id = str(message.author.id)
    display_name = message.author.display_name
    
    # Fire-and-forget alias tracking
    asyncio.create_task(
        self.container.alias_manager.track_alias(server_id, user_id, display_name)
    )
    
    # Continue existing flow...
```

---

## Tasks

| ID | Task | Status |
|----|------|--------|
| 1.1 | Create `alias_storage.py` with Markdown parsing | Pending |
| 1.2 | Create `alias_manager.py` with cache layer | Pending |
| 1.3 | Add asyncio.Lock per server | Pending |
| 1.4 | Integrate into `dependencies.py` | Pending |
| 1.5 | Hook into `chat_gateway.py` | Pending |
| 1.6 | Create `memories/INDEX.md` template | Pending |
| 1.7 | Unit tests for storage parsing | Pending |
| 1.8 | Integration tests for tracking flow | Pending |

---

## Testing

### Unit Tests: `tests/unit/test_alias_storage.py`
- Parse Markdown table correctly
- Handle Unicode names (Hòa, Dũng)
- Handle empty/missing file
- Lock contention

### Integration Tests: `tests/integration/test_alias_flow.py`
- Send message → alias tracked
- Resolve alias → correct user_id
- Cross-server alias isolation