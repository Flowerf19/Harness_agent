# Manual Test Scripts cho Bé Bảy

Các script test hệ thống trí nhớ của bot với **kết nối thật** (không mock).

## Prerequisites

Trước khi chạy test:

1. **Discord Bot Token**: Set trong `.env` (`DISCORD_LLM_BOT_TOKEN`)
2. **Redis**: Chạy tại `REDIS_URL` (default: `redis://localhost:6379`)
3. **Qdrant**: Chạy tại `QDRANT_URL` (default: `http://localhost:6333`)
4. **Conda Environment**: `discord_bot` activated

```bash
conda activate discord_bot
```

## Quick Start: Check All Services

```bash
python tests/manual/check_services.py
```

Kiểm tra tất cả services đang chạy trước khi test.

## Test Scripts

### 1. check_services.py

**Purpose**: Xác minh tất cả services kết nối được.

```bash
python tests/manual/check_services.py
```

**Expected Output**:
- ✅ Redis: Connected
- ✅ Qdrant: Connected
- ✅ Discord Token: Valid

**Troubleshooting**:
- Redis fail: `docker start redis` hoặc `redis-server`
- Qdrant fail: `docker start qdrant` hoặc check http://localhost:6333/dashboard

---

### 2. test_overflow_flow.py

**Purpose**: Mô phỏng T1 (Active Memory) overflow trigger.

**Flow**:
1. Kết nối Redis
2. Thêm message đến khi đạt token limit (2000)
3. Overflow trigger fire
4. Snapshot được queue cho Evernight agent
5. (Optional) Trigger Evernight consolidation → check Qdrant

```bash
python tests/manual/test_overflow_flow.py --user-id 123456789
```

**Arguments**:
- `--user-id`: Discord user ID (required)
- `--skip-consolidation`: Bỏ qua bước consolidation
- `--verbose`: Log chi tiết

---

### 3. test_nightly_trigger.py

**Purpose**: Test scheduled nightly consolidation mechanism.

```bash
python tests/manual/test_nightly_trigger.py
```

**Arguments**:
- `--user-id`: Specific user ID (optional)
- `--verbose`: Log chi tiết

> **Note**: Đang được migrate từ nightly trigger (2AM) sang inactivity trigger (30 phút không chat). Script này test legacy mechanism.

---

### 4. test_search_wiki.py

**Purpose**: Xác minh WikiPages trong Qdrant searchable.

```bash
python tests/manual/test_search_wiki.py --user-id 123456789 --topic Evangelion
```

**Arguments**:
- `--user-id`: Discord user ID (required)
- `--topic`: Topic cần search (required)
- `--top-k`: Số kết quả (default: 5)
- `--verbose`: Log chi tiết

---

## Common Issues

### Redis Connection Failed

```bash
docker run -d --name redis -p 6379:6379 redis:alpine
```

### Qdrant Connection Failed

```bash
docker run -d --name qdrant -p 6333:6333 qdrant/qdrant
```

### Discord Token Invalid

1. https://discord.com/developers/applications
2. Create bot hoặc reset token
3. Copy token vào `.env`

### Embedding Model Not Found

Model được download tự động lần đầu chạy. Cần:
- Internet connection
- `HF_TOKEN` trong `.env` (nếu model gated)
- ~500MB disk (Qwen3-Embedding-0.6B)

---

## Test Data Cleanup

```bash
# Xóa T1 data của user
redis-cli DEL "active_memory:123456789"

# Xóa WikiPages: dùng Qdrant dashboard hoặc API
```

---

## Architecture Reference

Các test này mô phỏng **Twin-Soul Agent Architecture**:

```
┌─────────────────────────────────────────────────────────────┐
│                    GATEWAY ORCHESTRATOR                     │
│              (python -m gateway)                            │
└──────────────────────────┬──────────────────────────────────┘
                           │ A2A Protocol
          ┌────────────────┴────────────────┐
          ▼                                 ▼
┌─────────────────────┐          ┌─────────────────────┐
│   MARCH7 AGENT      │   A2A    │   EVERNIGHT AGENT   │
│   Trợ lý chính       │◄────────►│   Self-Healing      │
│   Port 8000         │          │   Port 8001         │
│                     │          │                     │
│  ┌───────────────┐  │          │  ┌───────────────┐  │
│  │ T1 (Redis)    │  │          │  │ Inactivity     │  │
│  │ Active Memory │  │          │  │ Trigger (60s)  │  │
│  └───────────────┘  │          │  └───────────────┘  │
│  ┌───────────────┐  │          │  ┌───────────────┐  │
│  │ T3 (YAML)     │  │          │  │ T2 (Qdrant)   │  │
│  │ Core Memory   │  │          │  │ WikiPages      │  │
│  └───────────────┘  │          │  └───────────────┘  │
└─────────────────────┘          └─────────────────────┘
```

- **March7 Agent**: Hội thoại, tool calling, quản lý T1 (Redis) + T3 (YAML)
- **Evernight Agent**: Background — giám sát lỗi, self-healing, consolidation T2 (Qdrant)
- **A2A Protocol**: Hai agent giao tiếp qua HTTP JSON-RPC + SSE
- **Inactivity Trigger**: Evernight poll Redis mỗi 60s, trigger consolidation sau 30 phút user không chat

---

## Notes

- Đây là **manual tests**, không phải pytest automated
- Dùng **kết nối thật** đến services giống production
- Dành cho **development validation** và **troubleshooting**
- KHÔNG chạy với production database nếu chưa hiểu impact
