The user wants me to analyze the conversation history and generate a comprehensive project summary in markdown format. Let me review the conversation to extract the key information:

1. **Overall Goal**: The user is working on a Discord bot with a 3-tier memory architecture (T1, T2, T3). The main focus was on fixing issues with the bot's memory system, specifically around reasoning models (like DeepSeek R1) and their impact on T1 memory overflow, as well as enhancing the search_memory tool.

2. **Key Knowledge**:
- Technology: Python Discord bot with Redis (T1), Qdrant (T2), YAML (T3) storage
- Architecture: 3-tier memory system - T1 (Active Memory/short-term), T2 (Wiki Pages/long-term), T3 (Core Memory/profile)
- Tools: search_memory, web_search, update_user_profile, update_personality
- Testing: Use `conda run -n discord_bot pytest` (not system Python)
- Docker: docker compose -f docker/docker-compose.yml up -d

3. **Recent Actions**:
- Fixed reasoning_content not being saved to T1 memory (added reasoning_only flag)
- Fixed OverflowQueue serialization (datetime not JSON serializable - use model_dump(mode='json'))
- Created TOOL.md for centralized tool guidance
- Enhanced search_memory with 3 modes: semantic, time, topic
- Enhanced embedding to include key_points and canonical_topic (not just current_summary)

4. **Current Plan**:
- Most tasks completed - tests passing
- Need to restart Docker to apply changes

Let me write a comprehensive summary.# Project Summary

## Overall Goal
Discord bot "Bé Bảy" (March 7th persona) với kiến trúc memory 3 tầng, đang debug và enhance hệ thống T2 Wiki Pages search.

## Key Knowledge

### Architecture
- **T1 (Active Memory)**: Redis storage, short-term conversation context, MAX_WORKING_TOKENS=2000, TARGET_SAFE_TOKENS=1000
- **T2 (Wiki Pages)**: Qdrant vector storage, consolidated topics via EvernightAgent
- **T3 (Core Memory)**: YAML profile files, user facts via update_user_profile tool

### Wiki Page Chunk Structure
| Field | Embedding? |
|-------|------------|
| `current_summary` | ✅ (main) |
| `key_points` | ✅ (concat) |
| `canonical_topic` | ✅ (concat) |
| `last_updated` | ❌ (timestamp filter) |
| `category` | ❌ (enum filter) |

### Commands
- **Tests**: `conda run -n discord_bot pytest tests/unit/ -v`
- **Docker**: `docker compose -f docker/docker-compose.yml up -d`
- **Restart**: `docker compose restart be_bay_bot`

### Files
- `memories/TOOL.md` - Centralized tool guide
- `memories/SOUL.md` - Conversation rules
- `memories/IDENTITY.md` - Bot persona

## Recent Actions

1. **Fixed reasoning models memory overflow**
   - Added `reasoning_only` flag to LLMResponse
   - Skip T1 save when `reasoning_only=True` (only show to user)
   - Files: `llm_response.py`, `lm_studio_service.py`, `chat_coordinator.py`

2. **Fixed OverflowQueue serialization**
   - `MemoryEntry` → use `model_dump(mode='json')` for datetime → ISO string
   - File: `overflow_queue.py`

3. **Created TOOL.md**
   - Centralized tool usage guide
   - Query transformation examples
   - File: `memories/TOOL.md`

4. **Enhanced search_memory with 3 modes**
   - `semantic`: embedding search (default)
   - `time`: filter by `last_updated` within X days
   - `topic`: filter by `canonical_topic` keyword
   - Files: `search_memory_tool.py`, `wiki_storage.py`

5. **Enhanced embedding coverage**
   - Before: only `current_summary`
   - After: `canonical_topic + current_summary + key_points`
   - File: `evernight/agent.py`

## Current Plan

1. [DONE] Fix reasoning models T1 overflow
2. [DONE] Fix OverflowQueue JSON serialization
3. [DONE] Create TOOL.md for tool guidance
4. [DONE] Add search modes (semantic/time/topic)
5. [DONE] Enhance embedding with key_points + topic
6. [TODO] Restart Docker to apply changes
7. [TODO] Test with real user queries

---

## Summary Metadata
**Update time**: 2026-04-28T08:15:10.685Z 
