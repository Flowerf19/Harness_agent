"""
Global pytest fixtures for Sub-Agent architecture tests.

This conftest.py provides all fixtures for testing:
- Mock Redis client (for T1 queue/storage)
- Mock LLM client (for tool calling and structured extraction)
- Mock Embedding service (for vector embeddings)
- Sample data fixtures (T1 snapshots, T2 models)

All fixtures use lazy imports inside fixture functions to avoid
heavy dependency imports (torch, sentence-transformers, etc.).

Usage in tests:
    def test_something(mock_redis, mock_llm_client):
        # Use fixtures directly
        ...
"""
import sys
from pathlib import Path
import json
from datetime import datetime, timezone

import pytest
from unittest.mock import AsyncMock, MagicMock

# Ensure src module is importable
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# ============================================================
# Sample Data Fixtures
# ============================================================

@pytest.fixture
def sample_user_id() -> str:
    """Test Discord user ID."""
    return "123456789012345678"


@pytest.fixture
def sample_message_user() -> dict:
    """Sample user message from T1 memory."""
    return {
        "role": "user",
        "content": "I just finished watching Evangelion! The ending was mind-blowing.",
        "timestamp": "2025-01-15T10:30:00Z",
        "metadata": {
            "channel_id": "987654321",
            "guild_id": "111222333",
        },
    }


@pytest.fixture
def sample_message_assistant() -> dict:
    """Sample assistant message from T1 memory."""
    return {
        "role": "assistant",
        "content": "Evangelion is a classic! What did you think about the ending?",
        "timestamp": "2025-01-15T10:30:05Z",
        "metadata": {
            "channel_id": "987654321",
            "guild_id": "111222333",
        },
    }


@pytest.fixture
def sample_t1_snapshot(
    sample_user_id: str,
    sample_message_user: dict,
    sample_message_assistant: dict,
) -> list[dict]:
    """
    Sample T1 memory snapshot (overflow from Active Memory).

    This represents messages extracted from T1 (Redis-based active memory)
    that need to be consolidated into T2 memory.
    """
    return [
        {
            "role": "user",
            "content": "I started watching Neon Genesis Evangelion last week",
            "timestamp": "2025-01-10T08:00:00Z",
        },
        {
            "role": "assistant",
            "content": "Oh nice! Evangelion is a classic mecha anime. How far are you?",
            "timestamp": "2025-01-10T08:00:05Z",
        },
        {
            "role": "user",
            "content": "I'm on episode 14. The story is getting really intense!",
            "timestamp": "2025-01-12T15:30:00Z",
        },
        {
            "role": "assistant",
            "content": "Episode 14 is where things really start to get psychological. Enjoy the ride!",
            "timestamp": "2025-01-12T15:30:05Z",
        },
        sample_message_user,
        sample_message_assistant,
    ]


@pytest.fixture
def sample_t2_page(sample_user_id: str):
    """Sample T2 page for tests."""
    from twin.shared.memories.t2.models import T2Page, generate_topic_id

    now = datetime.now(timezone.utc)
    topic_id = generate_topic_id(sample_user_id, "Evangelion_Anime")
    return T2Page(
        page_id=topic_id,
        user_id=sample_user_id,
        topic_id=topic_id,
        canonical_topic="Evangelion_Anime",
        category="entertainment",
        current_summary="User is watching Neon Genesis Evangelion and finds it intense and mind-blowing.",
        key_points=[
            "Started watching Evangelion in January 2025",
            "Currently on episode 14",
            "Finds the story psychological and intense",
            "Finished the series and found the ending mind-blowing",
        ],
        importance=4,
        ttl_days=60,
        created_at=datetime(2025, 1, 10, 8, 0, 0, tzinfo=timezone.utc),
        updated_at=now,
        last_accessed=now,
        access_count=3,
        history_log=[
            "added: started watching Evangelion",
            "updated: episode 14 reached",
            "updated: finished series",
        ],
        confidence=0.95,
    )


@pytest.fixture
def sample_snapshot(sample_t1_snapshot):
    """Alias for sample_t1_snapshot for backward compatibility."""
    return sample_t1_snapshot


# ============================================================
# Redis Fixtures
# ============================================================

@pytest.fixture
def mock_redis():
    """
    Mock Redis client using AsyncMock.

    Provides common Redis operations used by MemoryJobQueue:
    - lpush, rpop, llen, lrange (queue operations)
    - hset, hget, hdel (checkpoint operations)
    - delete (clear operations)

    Supports both:
    1. Internal state via _queue and _checkpoints (for integration-like tests)
    2. return_value override (for unit tests that need specific responses)
    """
    redis = AsyncMock()
    redis._queue = []
    redis._checkpoints = {}

    async def mock_lpush(key, value):
        redis._queue.insert(0, value)

    async def mock_rpop(key):
        # Check if return_value was explicitly set (not None default)
        if redis.rpop._return_value is not None:
            return redis.rpop._return_value
        if redis._queue:
            return redis._queue.pop()
        return None

    async def mock_llen(key):
        # Check if return_value was explicitly set
        if redis.llen._return_value is not None:
            return redis.llen._return_value
        return len(redis._queue)

    async def mock_lrange(key, start, end):
        # Check if return_value was explicitly set
        if redis.lrange._return_value is not None:
            return redis.lrange._return_value
        if end == -1:
            return redis._queue[start:]
        return redis._queue[start : end + 1]

    async def mock_hset(key, field, value):
        redis._checkpoints[field] = value

    async def mock_hget(key, field):
        # Check if return_value was explicitly set
        if redis.hget._return_value is not None:
            return redis.hget._return_value
        return redis._checkpoints.get(field)

    async def mock_hdel(key, field):
        if field in redis._checkpoints:
            del redis._checkpoints[field]

    async def mock_delete(key):
        redis._queue = []

    redis.lpush = AsyncMock(side_effect=mock_lpush)
    redis.rpop = AsyncMock(side_effect=mock_rpop)
    redis.rpop._return_value = None  # Track explicit return_value
    redis.llen = AsyncMock(side_effect=mock_llen)
    redis.llen._return_value = None
    redis.lrange = AsyncMock(side_effect=mock_lrange)
    redis.lrange._return_value = None
    redis.hset = AsyncMock(side_effect=mock_hset)
    redis.hget = AsyncMock(side_effect=mock_hget)
    redis.hget._return_value = None
    redis.hdel = AsyncMock(side_effect=mock_hdel)
    redis.delete = AsyncMock(side_effect=mock_delete)

    # Helper to set return_value and mark it as explicitly set
    def set_return_value(method_name, value):
        method = getattr(redis, method_name)
        method._return_value = value
        method.return_value = value

    redis.set_return_value = set_return_value

    def reset_storage():
        redis._queue = []
        redis._checkpoints = {}
        # Reset return_value markers
        redis.rpop._return_value = None
        redis.llen._return_value = None
        redis.lrange._return_value = None
        redis.hget._return_value = None

    redis.reset_storage = reset_storage
    return redis


@pytest.fixture
def redis_client(mock_redis):
    """Alias for mock_redis for clearer test semantics."""
    return mock_redis


@pytest.fixture
def overflow_queue(mock_redis):
    """MemoryJobQueue instance with mock Redis."""
    from twin.shared.memories.t2.queue import MemoryJobQueue

    return MemoryJobQueue(mock_redis)


# ============================================================
# LLM Fixtures
# ============================================================

@pytest.fixture
def topic_extraction_response() -> dict:
    """Sample JSON response for topic extraction from T1 snapshot."""
    return {
        "topics": [
            {
                "canonical_topic": "Evangelion_Anime",
                "category": "entertainment",
                "summary": "User is watching Neon Genesis Evangelion and finds it intense and mind-blowing.",
                "key_points": [
                    "Started watching Evangelion in January 2025",
                    "Finished the series",
                    "Found the ending mind-blowing",
                ],
                "importance": 4,
                "confidence": 0.95,
            }
        ]
    }


@pytest.fixture
def merge_response() -> dict:
    """Sample JSON response for T2 summary update operation."""
    return {
        "current_summary": "User finished Neon Genesis Evangelion and found the ending mind-blowing. The psychological aspects were particularly impactful.",
        "key_points": [
            "Started watching Evangelion in January 2025",
            "Finished the entire series",
            "Found the ending mind-blowing",
            "Appreciated the psychological depth",
        ],
        "history_log": [
            "added: started watching Evangelion",
            "updated: finished series",
            "added: psychological depth appreciated",
        ],
        "category": "entertainment",
        "importance": 4,
    }


@pytest.fixture
def llm_response():
    """Factory fixture to create LLMResponse objects."""
    from twin.shared.llm.llm_response import LLMResponse

    def _create(
        content: str = "Test response",
        input_tokens: int = 0,
        output_tokens: int = 0,
        model: str = "test-model",
        finish_reason: str = "stop",
        tool_calls: list[dict] | None = None,
        reasoning_content: str | None = None,
        reasoning_only: bool = False,
    ) -> LLMResponse:
        return LLMResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            model=model,
            finish_reason=finish_reason,
            raw_response={},
            tool_calls=tool_calls,
            reasoning_content=reasoning_content,
            reasoning_only=reasoning_only,
        )

    return _create


@pytest.fixture
def mock_llm_client(llm_response):
    """Mock LLM client with configurable responses."""
    client = AsyncMock()
    client._responses = []
    client._response_index = 0

    async def mock_generate_response(messages, system_prompt=None, use_native_tools=False):
        if client._response_index < len(client._responses):
            response = client._responses[client._response_index]
            client._response_index += 1
            return response
        return llm_response(content="Default mock response")

    def add_response(content: str | dict, **kwargs):
        if isinstance(content, dict):
            content = json.dumps(content)
        client._responses.append(llm_response(content=content, **kwargs))

    def reset():
        client._responses = []
        client._response_index = 0

    client.generate_response = AsyncMock(side_effect=mock_generate_response)
    client.add_response = add_response
    client.reset = reset
    return client


# ============================================================
# Embedding Fixtures
# ============================================================

@pytest.fixture
def mock_embedding_service():
    """
    Mock embedding service.

    Returns a deterministic 1024-dim vector for testing.
    """
    service = AsyncMock()
    # Return a deterministic 1024-dim vector.
    service.get_embedding = AsyncMock(return_value=[0.1] * 1024)
    return service


# ============================================================
# Token Counter Fixtures
# ============================================================

@pytest.fixture
def mock_token_counter():
    """Mock token counter that returns a fixed token count."""
    counter = MagicMock()
    counter.count_entry_tokens = MagicMock(return_value=100)
    return counter


# ============================================================
# Cleanup Fixtures
# ============================================================

@pytest.fixture
def mock_smart_cleanup():
    """Mock SmartCleanup for T1 memory management."""
    cleanup = AsyncMock()
    cleanup.execute = AsyncMock()
    return cleanup


@pytest.fixture
def mock_context_builder():
    """Mock ContextBuilder for T1 context assembly."""
    builder = MagicMock()
    builder.build_context = MagicMock(return_value=[{"role": "user", "content": "test"}])
    return builder


@pytest.fixture
def mock_event_dispatcher():
    """Mock EventDispatcher for T1 events."""
    from twin.march7.memories.activate_memory.events.event_dispatcher import EventDispatcher
    return EventDispatcher()
