# Docker Setup

## Structure

```
docker/
├── Dockerfile           # Bot image definition
├── docker-compose.yml   # Service orchestration
├── README.md            # This file
└── volumes/             # Persistent data (bind mounts)
    ├── redis_data/      # Redis - Active Memory (T1)
    ├── qdrant_data/     # Qdrant - Episodic Memory (T2)
    ├── hf_cache/        # HuggingFace model cache
    └── conda_envs/      # Conda environment persistence
```

## Quick Start

### From docker/ folder:
```bash
cd docker
docker compose up -d
```

### From project root:
```bash
docker compose -f docker/docker-compose.yml up -d
```

## Services

| Service | Port | Purpose |
|---------|------|---------|
| `be_bay_redis` | 6379 | Active Memory (T1) - conversation context |
| `be_bay_qdrant` | 6333, 6334 | Episodic Memory (T2) - vector storage |
| `be_bay_bot` | - | Discord bot application |

## Commands

```bash
# Start all services
docker compose up -d

# Stop all services
docker compose down

# Rebuild bot image
docker compose build be_bay_bot

# View logs
docker compose logs -f be_bay_bot

# Restart bot
docker compose restart be_bay_bot
```

## Data Persistence

All data is stored in `docker/volumes/`:

- **redis_data/**: Redis append-only file (conversation history)
- **qdrant_data/**: Qdrant vectors (episodic memories)
- **hf_cache/**: Downloaded embedding models
- **conda_envs/**: Python environment (avoids reinstalling packages)

## Note

- Volume contents are excluded from git (see `.gitignore`)
- `.gitkeep` files preserve directory structure