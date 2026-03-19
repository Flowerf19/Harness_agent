# AI Agent Guide - Discord LLM Chatbot

## 1. Project Overview

This is a Discord AI Chatbot with a **Three-Tier Memory System** inspired by cognitive science. The bot features:

- **March 7th** persona from Honkai: Star Rail
- Adaptive memory that learns user preferences
- Multi-LLM support (Gemini, Qwen, Ollama)
- Smart typing simulation and anti-spam

## 2. Architecture Summary

### Core Pattern: Service-Repository with Dependency Injection

- `AppContainer` (dependencies.py): Singleton DI container
- `ChatCoordinator`: Main orchestrator for chat flow
- `MemoryManager`: Pub/Sub orchestrator for 3-tier memory

### Three-Tier Memory System

| Tier | Name | Storage | Purpose |
|------|------|---------|---------|
| T1 | Active Memory | RAM | Short-term context, token counting, message evaluation |
| T2 | Episodic Memory | Vector DB | Long-term RAG, event extraction, semantic search |
| T3 | Core Memory | YAML files | User profile, preferences, critical facts |

### Event Flow (Pub/Sub)

```
T1 detects critical info → Event: CRITICAL_INFO_DETECTED → T3 updates profile
T1 token limit reached → Event: TOKEN_LIMIT_REACHED → T2 summarizes → T1 cleans up
```

## 3. Key Files Reference

### Entry Points

- `src/bot.py` - Main bot entry, Cog auto-discovery
- `src/__main__.py` - Python module entry

### Configuration

- `src/config/settings.py` - All config from environment variables
- `config.py` - Root config loader
- `.env` - Environment variables (DISCORD_LLM_BOT_TOKEN, GEMINI_API_KEY, etc.)

### Core Services

- `src/services/dependencies.py` - DI container, initialization order
- `src/services/chat_coordinator.py` - Main chat orchestrator
- `src/services/memories/memory_manager.py` - Memory system orchestrator

### Memory System

- `src/services/memories/activate_memory/` - T1 (Active Memory)
- `src/services/memories/episodic_memory/` - T2 (Episodic Memory)
- `src/services/memories/core_memory/` - T3 (Core Memory)

### LLM Services

- `src/services/llm/base_llm_service.py` - Abstract interface
- `src/services/llm/gemini_service.py` - Google Gemini
- `src/services/llm/qwen_service.py` - Alibaba Qwen

### Discord Interface

- `src/cogs/chat_gateway.py` - Main message handler
- `src/cogs/user_commands.py` - User commands
- `src/cogs/admin_channels.py` - Admin commands

### Prompts

- `prompts/personality.yaml` - Bot personality (March 7th)
- `prompts/conversation_prompt.yaml` - Conversation guidelines

## 4. Coding Conventions

### Naming

- Files: `snake_case.py`
- Classes: `PascalCase`
- Functions/variables: `snake_case`
- Private methods: `_leading_underscore`
- Async functions: `async def` prefix

### Project Structure

```
src/
├── bot.py                 # Entry point
├── config/                # Settings and logging
├── cogs/                  # Discord.py Cogs
├── services/              # Business logic
│   ├── llm/               # LLM providers
│   ├── memories/          # 3-tier memory
│   └── dependencies.py    # DI container
└── utils/                 # Utilities
```

### Dependency Injection Pattern

```python
# Get singleton instance
container = AppContainer.get_instance()
coordinator = container.chat_coordinator
```

### Event Subscription Pattern (Memory System)

```python
# Subscribe to events
self.events.subscribe(
    ActiveMemoryEvent.CRITICAL_INFO_DETECTED,
    self.handle_critical_info
)

# Emit events
self.events.emit(
    ActiveMemoryEvent.CRITICAL_INFO_DETECTED,
    user_id,
    data={"entry": entry}
)
```

### LLM Response Handling

```python
# Always use generate_response with messages list
response = await self.llm.generate_response(
    messages=[{"role": "user", "content": "..."}],
    system_prompt="..."
)

# Handle both LLMResponse and string (for error cases)
if isinstance(response, LLMResponse):
    content = response.content
    tokens = response.total_tokens
else:
    content = response  # Error string
```

## 5. Environment Variables

Required:

- `DISCORD_LLM_BOT_TOKEN` - Discord bot token

Optional (choose at least one LLM):

- `GEMINI_API_KEY` - Google Gemini API
- `QWEN_API_KEY` - Alibaba Qwen API

Configuration:

- `LLM_PROVIDER` - "gemini" or "qwen" (default: gemini)
- `LLM_MODEL` - Model name (default: gemini-1.5-flash)
- `ENABLE_TYPING_SIMULATION` - "1" or "0" (default: "1")
- `TYPING_SPEED_WPM` - Words per minute (default: 250)

## 6. Common Tasks

### Adding a new LLM Provider

1. Create new service in `src/services/llm/`
2. Inherit from `BaseLLMService`
3. Implement `generate_response()` method
4. Add provider selection in `AppContainer.initialize()`

### Adding a new Memory Event

1. Add event type to `ActiveMemoryEvent` enum
2. Subscribe to event in `MemoryManager._wire_events()`
3. Emit event from `ActiveMemoryService`

### Adding a new Discord Command

1. Create new Cog in `src/cogs/`
2. Register in `bot.py` setup_hook()
3. Follow Discord.py Cog pattern

### Modifying Bot Personality

1. Edit `prompts/personality.yaml`
2. Edit `prompts/conversation_prompt.yaml`
3. Restart bot to reload

## 7. Debug Tips

### Enable verbose logging

```python
# In .env
LOG_LEVEL=DEBUG
```

### Trace with LangSmith

Set environment variables:
```
LANGCHAIN_API_KEY=your_key
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=discord-bot
```

### Check memory state

```python
# User commands
!status - Check bot status
!relationships - View user relationships
!conversation <user> - View conversation summary
```

## 8. Important Constraints

### Discord Message Limits

- Max 2000 characters per message
- Split long responses automatically
- Use typing indicator for delays

### Memory Token Limits

- T1 (Active): `MAX_WORKING_TOKENS` (default in constants.py)
- Triggers T2 summarization when exceeded

### Rate Limiting

- Anti-spam service in `src/services/core/anti_spam_service.py`
- Per-user locking in conversation manager

## 9. Future Roadmap

See README.MD for:

- Natural music interaction
- Server administration
- Image generation
- Custom agent platform