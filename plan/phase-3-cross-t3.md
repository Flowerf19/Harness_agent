# Phase 3: Cross T3 Retrieval

## Goal
Enable cross-user profile retrieval with 4-layer consent mechanism.

**Depends on:** Phase 1 + Phase 2

---

## Tool: `fetch_profile_tool.py`

### Location
`src/services/tools/implementations/fetch_profile_tool.py` (NEW)

### Schema
```python
class FetchProfileTool(BaseTool):
    name = "fetch_profile"
    description = "Fetch another user's public profile info"
    
    input_schema = {
        "type": "object",
        "properties": {
            "target_user_id": {
                "type": "string",
                "description": "Discord user ID to fetch profile for"
            },
            "target_name": {
                "type": "string",
                "description": "Display name (alternative to ID, will resolve via alias)"
            }
        },
        "required": ["target_user_id"]
    }
```

### Security Validation
```python
async def execute(self, target_user_id: str, target_name: str | None = None):
    # Get current context
    current_server_id = self._get_current_server_id()  # Injected by coordinator
    current_channel_id = self._get_current_channel_id()
    
    # Resolve name to ID if needed
    if target_name and not target_user_id:
        target_user_id = await self.alias_manager.resolve_alias(
            current_server_id, target_name
        )
        if not target_user_id:
            return "User not found in this server"
    
    # Cross-server validation
    if not await self._validate_same_server(current_server_id, target_user_id):
        return "Access denied: user not in this server"
    
    # Fetch T3 profile (Public section only)
    profile = await self.t3_manager.get_public_profile(target_user_id)
    return profile
```

---

## T3 Structure: Public/Private Sections

### Markdown Format
```markdown
# User Profile: Hòa

## Public Info
- Role: AI Engineer at DXTech
- Location: Ho Chi Minh City
- Skills: Python, Machine Learning

## Private Info
- Favorite food: Phở
- Notes: Prefers async communication
```

### Storage Changes

**Location:** `src/services/memories/core_memory/storage/markdown_storage.py` (MODIFY)

```python
class MarkdownStorage:
    async def get_public_profile(self, user_id: str) -> str:
        """Return only ## Public Info section"""
        content = await self.read(user_id)
        return self._extract_section(content, "Public Info")
    
    async def get_full_profile(self, user_id: str) -> str:
        """Return entire file (for user's own access)"""
        return await self.read(user_id)
    
    def _extract_section(self, content: str, section: str) -> str:
        # Parse markdown and extract section
        pass
```

---

## 4-Layer Consent Mechanism

### Layer 1: User Explicit Consent

**Tool:** `update_profile_tool.py` (MODIFY)

```python
input_schema = {
    "properties": {
        "fact": {"type": "string"},
        "category": {"type": "string"},
        "visibility": {
            "type": "string",
            "enum": ["public", "private"],
            "description": "Public (shareable) or Private (only for you)"
        }
    }
}
```

### Layer 2: Chat Space Context

**Location:** `src/services/chat_coordinator.py`

```python
# Default visibility based on channel type
if message.guild:  # Group
    default_visibility = "public"
else:  # DM
    default_visibility = "private"
```

### Layer 3: Evernight Nightly Review

**Location:** `src/agents/evernight/agent.py`

```python
async def review_profile_sections(self, user_id: str):
    """Nightly task to review and reclassify"""
    profile = await self.t3_manager.get_full_profile(user_id)
    
    # LLM review prompt
    prompt = f"""
    Review this user profile and ensure:
    - Public Info: professional info, skills, location
    - Private Info: personal preferences, emotions
    
    Profile: {profile}
    """
    
    reviewed = await self.llm.generate(prompt)
    await self.t3_manager.update_profile(user_id, reviewed)
```

### Layer 4: Hardcoded Rules

**Location:** `src/services/memories/core_memory/prompts.yaml`

```yaml
visibility_rules:
  always_public:
    - discord_id
    - display_name
    - role_in_server
    - professional_links
  always_private:
    - medical_info
    - financial_info
    - personal_emotions
    - daily_chat_logs
```

---

## Tasks

| ID | Task | Status |
|----|------|--------|
| 3.1 | Create `fetch_profile_tool.py` | ✅ Completed |
| 3.2 | Add cross-server validation | ✅ Completed |
| 3.3 | Modify `markdown_storage.py` for sections | ✅ Completed |
| 3.4 | Add `visibility` field to `update_profile_tool.py` | ✅ Completed |
| 3.5 | Implement Layer 2 (chat space default) | ✅ Completed |
| 3.6 | Add Layer 4 (hardcoded rules) | ✅ Completed |
| 3.7 | Register tool in `tool_registry.py` | ✅ Completed |
| 3.8 | Update System Prompt with visibility instruction | ✅ Completed |
| 3.9 | Security tests | Pending |

---

## Security Testing

### Test Cases
1. Same server → access granted
2. Cross-server → access denied
3. DM user profile → only public section returned
4. User marks private → not returned to others
5. LLM reclassify → Evernight respects rules