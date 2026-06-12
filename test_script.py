import asyncio
import logging

logging.basicConfig(level=logging.DEBUG)

from twin.shared.memory.timeline.models import T2Memory
from twin.shared.memory.profile.promotion_guard import ProfilePromotionGuard
from twin.shared.memory.timeline.consolidator import CandidateMemory

class FakeStore:
    async def knn_memories(self, *args, **kwargs):
        return []

class FakeProfileStore:
    def __init__(self):
        self.appender_recorder = []
    async def read_raw(self, user_id):
        return "## Sở thích\n- Fake bullet"
    async def append_raw(self, user_id, section, content):
        self.appender_recorder.append((user_id, section, content))
        print("APPENDED!")

async def main():
    store = FakeStore()
    profile_store = FakeProfileStore()
    guard = ProfilePromotionGuard(store, profile_store, None)
    
    memory = T2Memory(
        user_id="u1",
        content="Tên người dùng là Hoà.",
        embedding=[],
        topic_ids=[],
        catalogs=["identity"],
        speaker="user",
        importance=5,
        confidence=0.9,
    )
    
    res = await guard.process_candidate("u1", memory)
    print("RES:", res)
    print("RECORDER:", profile_store.appender_recorder)

asyncio.run(main())
