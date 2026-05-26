import json

import pytest

from twin.march7.memories.activate_memory.models import MemoryEntry
from twin.march7.memories.activate_memory.storage.redis_stack_storage import RedisStackStorage


class FakeRedis:
    def __init__(self):
        self.data = {}
        self.calls = []

    async def execute_command(self, *args):
        self.calls.append(args)
        cmd = args[0]

        if cmd == "FT.INFO":
            raise RuntimeError("no index")

        if cmd == "FT.CREATE":
            return "OK"

        if cmd == "JSON.SET":
            key = args[1]
            payload = args[3]
            self.data[key] = payload
            return "OK"

        if cmd == "JSON.GET":
            return self.data.get(args[1])

        if cmd == "FT.SEARCH":
            query = args[2]
            parts = query.split()
            scope = parts[0].removeprefix("@scope:{").removesuffix("}")
            scope_id = parts[1].removeprefix("@scope_id:{").removesuffix("}")
            keys = []
            for key, payload in self.data.items():
                data = json.loads(payload)
                if data["scope"] == scope and data["scope_id"] == scope_id:
                    keys.append((data["created_at_ts"], key))
            keys.sort()
            response = [len(keys)]
            for _, key in keys:
                response.append(key)
            return response

        raise RuntimeError(f"unsupported command: {cmd}")

    async def expire(self, _key, _ttl):
        return True

    async def delete(self, *keys):
        for key in keys:
            self.data.pop(key, None)
        return len(keys)

    async def scan_iter(self, pattern):
        prefix = pattern[:-1]
        for key in list(self.data.keys()):
            if key.startswith(prefix):
                yield key


@pytest.mark.asyncio
async def test_redis_stack_storage_save_and_get_entries_sorted():
    redis = FakeRedis()
    storage = RedisStackStorage(redis)
    await storage.initialize()

    a = MemoryEntry(user_id="u1", role="user", content="hi", tokens=2)
    b = MemoryEntry(user_id="u1", role="assistant", content="hello", tokens=3)

    await storage.save_entry(a)
    await storage.save_entry(b)

    entries = await storage.get_entries("u1")
    assert len(entries) == 2
    assert entries[0].entry_id == a.entry_id
    assert entries[1].entry_id == b.entry_id
    assert await storage.get_total_tokens("u1") == 5

    channel = MemoryEntry(
        scope="channel",
        scope_id="c1",
        user_id="u2",
        role="user",
        author_id="u2",
        author_name="Flowerf",
        channel_id="c1",
        content="channel note",
        tokens=4,
    )
    await storage.save_entry(channel)

    channel_entries = await storage.get_entries("channel", "c1")
    assert len(channel_entries) == 1
    assert channel_entries[0].entry_id == channel.entry_id
    assert await storage.get_total_tokens("channel", "c1") == 4


@pytest.mark.asyncio
async def test_redis_stack_storage_channel_scope_round_trips_assistant_role():
    redis = FakeRedis()
    storage = RedisStackStorage(redis)
    await storage.initialize()

    bot_reply = MemoryEntry(
        scope="channel",
        scope_id="c1",
        user_id="march7",
        role="assistant",
        author_id="march7",
        author_name="March7",
        channel_id="c1",
        content="2080 nha",
        tokens=2,
    )
    await storage.save_entry(bot_reply)

    entries = await storage.get_entries("channel", "c1")
    assert len(entries) == 1
    assert entries[0].role == "assistant"
    assert entries[0].author_name == "March7"
    assert entries[0].content == "2080 nha"
