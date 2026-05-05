# Phase 4: Nightly Maintenance

## Goal
Automated cleanup and restructuring via Evernight background tasks.

**Depends on:** Phase 1, 2, 3 (can parallel with Phase 3)

---

## Trigger: `nightly_trigger.py`

**Location:** `src/tasks/nightly_trigger.py` (MODIFY)

```python
async def run_nightly_tasks(self):
    """Run all nightly maintenance tasks"""
    
    # Alias cleanup
    await self.alias_manager.cleanup_stale_aliases()
    
    # T3 section review
    await self.evernight.review_all_profiles()
    
    # Channel context cleanup
    await self.channel_context.cleanup_inactive_channels()
    
    # Wiki consolidation (existing)
    await self.evernight.process_overflow_queue()
```

---

## Alias Cleanup

**Location:** `src/services/memories/alias_manager.py` (MODIFY)

```python
async def cleanup_stale_aliases(self):
    """Remove aliases not seen in 30 days"""
    threshold_days = 30
    
    for server_id in await self.storage.list_servers():
        directory = await self.storage.get_server_directory(server_id)
        
        for user in directory["members"]:
            # Check last activity (needs tracking)
            if user["last_seen_days"] > threshold_days:
                # Remove stale aliases
                await self.storage.remove_alias(server_id, user["user_id"])
```

---

## T3 Section Review

**Location:** `src/agents/evernight/agent.py` (MODIFY)

```python
async def review_all_profiles(self):
    """Review T3 profiles and reclassify sections"""
    users = await self.t3_manager.list_all_users()
    
    for user_id in users:
        profile = await self.t3_manager.get_full_profile(user_id)
        
        # LLM review
        reviewed = await self._llm_review_sections(profile)
        
        # Apply hardcoded rules
        reviewed = self._apply_visibility_rules(reviewed)
        
        # Update profile
        await self.t3_manager.update_profile(user_id, reviewed)
```

---

## Channel Context Cleanup

**Location:** `src/services/memories/channel_context.py` (MODIFY)

```python
async def cleanup_inactive_channels(self):
    """Remove channels inactive for 24h"""
    threshold_hours = 24
    
    for channel_id in self._participants.keys():
        last_activity = self._last_activity.get(channel_id)
        
        if last_activity and (now - last_activity) > threshold_hours:
            del self._participants[channel_id]
            del self._last_activity[channel_id]
            
            # Also clear T1 memory for channel
            await self.t1.clear_channel(channel_id)
```

---

## Tasks

| ID | Task | Status |
|----|------|--------|
| 4.1 | Add alias cleanup task | ✅ Completed |
| 4.2 | Add T3 section review task | ✅ Completed |
| 4.3 | Add channel context cleanup | ✅ Completed |
| 4.4 | Track last activity timestamps | ✅ Completed |
| 4.5 | Integrate into `nightly_trigger.py` | ✅ Completed |
| 4.6 | Add cleanup thresholds config | ✅ Completed |
| 4.7 | Logging for cleanup operations | ✅ Completed |
| 4.8 | Integration tests | Pending |

---

## Configuration

**Location:** `config.py` (MODIFY)

```python
# Cleanup thresholds
ALIAS_STALE_DAYS = 30
CHANNEL_INACTIVE_HOURS = 24
PROFILE_REVIEW_ENABLED = True
```

---

## Testing

### Scenarios
1. Alias not seen in 30 days → removed
2. Channel inactive 24h → cleaned
3. Profile with misclassified info → reviewed
4. Nightly trigger runs → all tasks executed

---

## Implementation Summary (Completed)

### Files Modified

| File | Changes |
|------|---------|
| `src/config/settings.py` | Added cleanup thresholds (ALIAS_STALE_DAYS, CHANNEL_INACTIVE_HOURS, PROFILE_REVIEW_ENABLED, PROFILE_REVIEW_BATCH_SIZE) |
| `src/services/memories/alias_storage.py` | Added `list_servers()`, `remove_alias()`, `update_last_activity()`, `get_stale_aliases()` + `last_seen` column to INDEX.md |
| `src/services/memories/alias_manager.py` | Added `cleanup_stale_aliases()` method + `last_seen` tracking in `_update_cache()` |
| `src/services/memories/channel_context.py` | Added `cleanup_inactive_channels_async()` with optional T1 memory clearing |
| `src/services/memories/core_memory/storage/markdown_storage.py` | Added `list_all_users()` for batch profile review |
| `src/agents/evernight/agent.py` | Added `review_profile_sections()`, `review_all_profiles()` + visibility rules |
| `src/tasks/nightly_trigger.py` | Added `set_cleanup_services()`, `run_nightly_tasks()` integrating all cleanup tasks |
| `src/services/dependencies.py` | Added cleanup services configuration for NightlyTrigger |

### Key Features

1. **Alias Cleanup**: Removes aliases not seen in configurable threshold days (default 30)
2. **Channel Cleanup**: Removes inactive channels with optional T1 memory clearing
3. **T3 Profile Review**: LLM-based visibility review with hardcoded Layer 4 rules
4. **Batch Processing**: Profile review limited to batch_size per night (default 10)
5. **Graceful Error Handling**: Each task continues if others fail
6. **Comprehensive Logging**: Stats logged for each cleanup operation