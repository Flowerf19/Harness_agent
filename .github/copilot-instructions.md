# Discord LLM AI Chatbot - Project Guidelines

## Project Overview

Discord bot powered by Google Gemini and Qwen with a 3-tier memory system, relationship tracking, and user profiles. Built with Service-Repository Pattern and Dependency Injection.

## Environment Setup

### Prerequisites
- **Python**: 3.14.3 (local development)
- **Conda**: Required for environment management
- **Docker**: Optional, for containerized deployment

### Required Environment Variables

See `.env.example` for all required variables:
- `DISCORD_TOKEN` - Discord bot token
- `GEMINI_API_KEY` - Google Gemini API key
- `PHOENIX_COLLECTOR_ENDPOINT` - Arize Phoenix endpoint (default: http://localhost:4317)
- `TOOL_LLM_ENDPOINT` - Local LLM endpoint (default: http://localhost:1234/v1)

## Project Structure

```
src/
├── bot.py                    # Entry point - Discord bot setup
├── __main__.py              # Python module entry
│
├── config/
│   ├── settings.py          # Config class (env variables)
│   └── logging_config.py    # Logging setup
│
├── cogs/                    # Discord Cogs (Event handlers)
│   ├── chat_gateway.py      # Main message handler
│   ├── user_commands.py     # User slash commands
│   └── admin_channels.py    # Admin channel management
│
├── services/
│   ├── chat_coordinator.py  # Main orchestrator
│   ├── dependencies.py      # DI Container (AppContainer)
│   │
│   ├── core/
│   │   └── anti_spam_service.py
│   │
│   ├── llm/                 # LLM Providers
│   │   ├── base_llm_service.py
│   │   ├── gemini_service.py
│   │   ├── qwen_service.py
│   │   └── embedding_service.py
│   │
│   └── memories/            # 3-Tier Memory System
│       ├── memory_manager.py
│       ├── activate_memory/ # Tier 1: Active Memory (RAM)
│       ├── episodic_memory/ # Tier 2: Episodic Memory (Vector DB)
│       └── core_memory/     # Tier 3: Core Memory (YAML DB)
│
└── utils/
    └── helpers.py

data/
├── bot_channels.json        # Bot channel configurations
└── core_memory/             # User profile storage (YAML)

memories/                    # Agent memory files (documentation)
plan/                        # Implementation plans
```

## Running the Bot

### Local Development

```bash
# Ensure conda environment is active
conda activate discord_bot

# Run the bot
python src/bot.py

# Or as module
python -m src
```

### Docker Deployment

```bash
# Build and run
docker-compose up -d

# View logs
docker-compose logs -f be_bay_bot

# Stop
docker-compose down
```

## Architecture Patterns

### 3-Tier Memory System

1. **Active Memory (RAM)**: Current conversation context
   - Message evaluation pipeline
   - Token counting and auto-cleanup
   - Events: `CRITICAL_INFO_DETECTED`, `TOKEN_LIMIT_REACHED`

2. **Episodic Memory (Vector DB)**: Long-term memory
   - Event extraction using LLM
   - Semantic search with Qwen3-Embedding-0.6B
   - Threshold: 0.4 similarity

3. **Core Memory (YAML DB)**: User profiles
   - Smart updates via LLM
   - Auto-injected into system prompts

### Service Layer

- **ChatCoordinator**: Main orchestrator for message processing
- **Dependency Injection**: Use `AppContainer` from `services/dependencies.py`
- **LLM Services**: Abstract base class with Gemini and Qwen implementations

## Code Conventions

### Imports

```python
# Standard library
import os
from typing import Optional, List

# Third-party
import discord
from discord.ext import commands

# Local imports (use absolute imports from src/)
from services.chat_coordinator import ChatCoordinator
from services.memories.memory_manager import MemoryManager
```

### Async Patterns

All service methods interacting with Discord or LLM APIs must be async:

```python
async def process_message(self, user_id: str, content: str) -> str:
    # Implementation
    pass
```

### Configuration Access

```python
from config.settings import Settings

settings = Settings()  # Singleton pattern
api_key = settings.gemini_api_key
```

## Key Files to Understand

- `src/services/chat_coordinator.py` - Main message processing logic
- `src/services/memories/memory_manager.py` - Memory orchestration
- `src/cogs/chat_gateway.py` - Discord message handler
- `src/services/dependencies.py` - DI container setup

## Testing

```bash
# Run tests
pytest

# Run with coverage
pytest --cov=src tests/
```

## Common Tasks

### Adding a new LLM provider

1. Create new service in `src/services/llm/`
2. Inherit from `BaseLLMService`
3. Implement `generate_response()` method
4. Register in `dependencies.py`

### Adding a new Discord command

1. Create or use existing cog in `src/cogs/`
2. Use `@commands.slash_command()` decorator
3. Register cog in `src/bot.py`

### Modifying memory behavior

- **Active Memory**: `src/services/memories/activate_memory/`
- **Episodic Memory**: `src/services/memories/episodic_memory/`
- **Core Memory**: `src/services/memories/core_memory/`

## Documentation

- `README.MD` - Full architecture documentation with diagrams
- `memories/` - Agent memory and identity documentation
- `plan/` - Implementation plans and upgrade notes