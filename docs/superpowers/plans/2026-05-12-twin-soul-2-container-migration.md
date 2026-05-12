# Twin-Soul: March7 + Evernight 2-Container Architecture

> **Plan:** Split from 1 container → 2 independent containers with separate Discord bots, A2A HTTP routing, and self-healing.

## Kiến trúc cuối cùng

| Container | Discord Bot | Vai trò | Port |
|-----------|-------------|---------|------|
| **march7** | Bé Bảy (token riêng) | Trợ lý chính — server channels | 8000 |
| **evernight** | Evernight (token riêng) | DM + self-healing + consolidation | 8001 |

**Routing Discord:**
- Message thường → March7 respond
- `!9 <nội dung>` → Evernight respond (ở server channel hoặc DM đều được)
- March7 ignore `!9` prefix, Evernight ignore message không có `!9` hoặc mention

**Bash Executor:**
- Mọi `execute_host_bash` → gửi DM tới Evernight bot để user approve
- Approval UI qua Discord buttons (approve/reject)

**Self-healing:**
- Evernight poll A2A health của March7 (`GET http://march7:8000/.well-known/agent.json`)
- Nếu fail → Evernight dùng `execute_host_bash` → `docker restart march7`
- Notify user qua DM khi restart

**A2A Communication:**
- March7 ↔ Evernight qua A2A HTTP (port 8000 + 8001)
- Discord handler trong March7 container gọi Evernight qua A2A HTTP cho `!9` messages

---

## Phase 1: Discord Bot Token cho Evernight

### Task 1: Tạo Discord bot Evernight trên Developer Portal
- [ ] Tạo application mới trên https://discord.com/developers/applications
- [ ] Tạo bot, copy token
- [ ] Set token vào `.env` file: `DISCORD_EVERNIGHT_TOKEN=xxx`
- [ ] Invite bot vào server với quyền đọc/gửi message

---

## Phase 2: Container Naming + Docker Compose

### Task 2: Rename containers từ `march7_twin` → `march7`, thêm `evernight`

**Files:**
- Modify: `docker/docker-compose.bot.yml` → đổi `container_name: march7_twin` → `march7`
- Create: `docker/docker-compose.evernight.yml`

**docker-compose.evernight.yml:**
```yaml
services:
  evernight:
    build:
      context: ../
      dockerfile: docker/twin/Dockerfile
    container_name: evernight
    restart: unless-stopped
    networks:
      - march7_net
    ports:
      - "8001:8001"
    depends_on:
      redis:
        condition: service_healthy
      qdrant:
        condition: service_healthy
    env_file:
      - ../.env
    environment:
      - DISCORD_EVERNIGHT_TOKEN=${DISCORD_EVERNIGHT_TOKEN}
      - REDIS_ENABLED=true
      - REDIS_URL=redis://redis:6379
      - REDIS_DB=1
      - QDRANT_URL=http://qdrant:6333
      - AGENT_NAME=evernight
      - LM_STUDIO_API_URL=http://host.docker.internal:1234/v1
      - TOOL_LLM_ENDPOINT=http://host.docker.internal:1234/v1
      - TOOL_LLM_MODEL=qwen3-coder-30b-a3b-instruct
      - BASH_EXECUTOR_URL=http://bash_executor:8374
      - BASH_EXECUTOR_TIMEOUT=30
      - MARCH7_URL=http://march7:8000
      - SELF_HEAL_ENABLED=true
      - SELF_HEAL_INTERVAL=30
      - SELF_HEAL_TIMEOUT=10
      - INACTIVITY_SECONDS=1800
      - POLL_INTERVAL=60
    extra_hosts:
      - "host.docker.internal:host-gateway"
    volumes:
      - ../twin:/app/twin:z
      - ../gateway:/app/gateway:z
      - ../memories:/app/memories:z
      - ../config.py:/app/config.py:z
      - ../.env:/app/.env:z
    healthcheck:
      test: ["CMD-SHELL", "pgrep -f 'python -m twin.evernight' || exit 1"]
      interval: 15s
      timeout: 5s
      retries: 3
      start_period: 30s
    logging:
      driver: "json-file"
      options:
        max-size: "100m"
```

**docker-compose.bot.yml (march7):**
- Remove `DISCORD_EVERNIGHT_TOKEN`
- Remove port `8001:8001`
- Add `EVERNIGHT_A2A_URL=http://evernight:8001`

### Task 3: Update docker-compose.yml master file
```yaml
include:
  - docker-compose.redis.yml
  - docker-compose.qdrant.yml
  - docker-compose.codebox.yml
  - docker-compose.bash-executor.yml
  - docker-compose.bot.yml
  - docker-compose.evernight.yml
```

---

## Phase 3: Entry Point — Evernight standalone

### Task 4: Tạo `twin/evernight/__main__.py`

Evernight chạy độc lập, không qua gateway:

```python
"""Entry point for Evernight agent: python -m twin.evernight"""
import asyncio
import signal
import logging
from dotenv import load_dotenv
load_dotenv(override=True)
from twin.shared.config.logging_config import setup_logging
setup_logging()
from twin.evernight.container import EvernightContainer
from twin.evernight.config import EvernightConfig
from twin.evernight.server.a2a_server import A2AServer
from twin.evernight.spawner import EvernightSpawner
from twin.evernight.triggers.inactivity_trigger import InactivityTrigger

async def main():
    config = EvernightConfig.from_env()
    container = EvernightContainer(config)
    await container.initialize()
    
    # Start A2A server on port 8001
    a2a_server = A2AServer(agent=container.agent, port=config.port)
    await a2a_server.start()
    
    # Start self-healing monitor
    if config.self_heal_enabled:
        from twin.evernight.self_heal.monitor import SelfHealMonitor
        monitor = SelfHealMonitor(
            march7_url=config.march7_url,
            interval=config.self_heal_interval,
            timeout=config.self_heal_timeout,
        )
        await monitor.start()
    
    # Start inactivity trigger
    inactivity = InactivityTrigger(container.agent, container.memory_manager)
    await inactivity.start()
    
    # Wait for shutdown
    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown_event.set)
    await shutdown_event.wait()
    
    await monitor.stop()
    await inactivity.stop()
    await a2a_server.stop()
    await container.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
```

### Task 5: Sửa March7 gateway __main__.py
- Chỉ boot `March7Container`
- Start A2A server trên port 8000
- Bỏ `EvernightContainer` init

---

## Phase 4: Discord Handler — Routing `!9` → Evernight

### Task 6: March7 handler detect `!9` → gọi Evernight qua A2A HTTP

**Files:**
- Modify: `gateway/adapters/discord/handler.py`
- Create: `gateway/adapters/discord/evernight_client.py` (A2A HTTP client)

**Flow:**
```
User: "!9 hello"
  → March7 adapter nhận message
  → Handler detect "!9" prefix
  → Handler gọi EvernightClient.send_chat(user_id, content)
  → A2A HTTP POST http://evernight:8001/
  → Evernight respond
  → Handler gửi response về channel
```

**March7 adapter ignore `!9`:**
- Trong `adapter.py` `on_message`: nếu content startswith `!9` → skip forward (để Evernight bot tự xử lý nếu nó ở cùng channel)
- Hoặc: Handler trong March7 vẫn route qua A2A HTTP cho `!9`

**Quyết định:** March7 handler vẫn route `!9` qua A2A HTTP → response gửi lại từ March7 bot. Đơn giản, không cần 2 bot cùng listen 1 channel.

### Task 7: Evernight Discord adapter (bot riêng)

**Files:**
- Create: `gateway/adapters/discord/evernight_adapter.py` (copy từ adapter.py, đổi bot_name)
- Modify: `gateway/adapters/factory.py` → tạo Evernight adapter khi có `DISCORD_EVERNIGHT_TOKEN`

Evernight bot:
- Listen DM + channel có `!9`
- Ignore message không có `!9` hoặc mention
- Gửi DM approval cho bash executor

---

## Phase 5: Bash Executor — DM Approval

### Task 8: Bash tool gửi DM xác nhận qua Evernight bot

**Flow:**
```
March7/Evernight gọi execute_host_bash
  → Bash executor trigger approval
  → Gửi DM tới user qua Evernight bot với buttons [Approve] [Reject]
  → User click button
  → Execute hoặc cancel
  → Gửi kết quả về channel gốc
```

**Files:**
- Modify: `twin/shared/tools/implementations/mcp/execute_host_bash.py`
- Modify: `gateway/adapters/discord/views/approve_view.py`
- Add DM routing: thay vì gửi response về channel gốc, gửi DM qua Evernight bot

---

## Phase 6: Self-Healing — Evernight giám sát March7

### Task 9: Self-heal monitor trong Evernight

**Files:**
- Create: `twin/evernight/self_heal/monitor.py`

```python
class SelfHealMonitor:
    async def start(self):
        # Poll March7 health every N seconds
        # If health check fails → execute_host_bash("docker restart march7")
        # Notify user via DM
```

**Health check:** `GET http://march7:8000/.well-known/agent.json`

**Recovery actions:**
1. Retry health check 3 lần
2. Nếu vẫn fail → `execute_host_bash("docker restart march7")`
3. DM user: "March7 vừa được restart do lỗi"

---

## Phase 7: Update Persona + Config

### Task 10: Update Evernight IDENTITY.md — nhắc đến Discord bot riêng
### Task 11: Update routing prefix từ `!e` → `!9` trong handler

---

## Rollback

Nếu có vấn đề:
```bash
cd ~/Projects/march7/docker
docker compose down
git checkout <commit-trước-đây>
docker compose up -d --build
```

---

## Thứ tự thực hiện

1. Phase 1: Tạo Discord token cho Evernight (user làm)
2. Phase 2: Docker compose (5 phút)
3. Phase 3: Entry point standalone (10 phút)
4. Phase 4: Discord handler + `!9` routing (15 phút)
5. Phase 5: Bash DM approval (15 phút)
6. Phase 6: Self-heal monitor (10 phút)
7. Phase 7: Update config + persona (5 phút)
