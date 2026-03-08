import asyncio
import logging

from dotenv import load_dotenv

# Load .env TRƯỚC khi import các module khác
load_dotenv()

# Enable logging để debug
logging.basicConfig(level=logging.DEBUG)

from src.services.dependencies import AppContainer  # noqa: E402


async def main():
    # 1. Kích hoạt Trạm điện
    container = AppContainer.get_instance()
    await container.initialize()

    coordinator = container.chat_coordinator
    memory_manager = container.memory_manager
    user_id = "test_user_123"

    print("\n=== DEBUG: KIỂM TRA SEMANTIC ENGINE ===")
    # Test SemanticEngine trực tiếp
    semantic_engine = memory_manager.t1.pipeline.semantic_engine
    print(f"Semantic Engine initialized: {semantic_engine._is_initialized}")
    print(f"Anchor vectors count: {len(semantic_engine._anchor_vectors)}")

    # Test evaluate
    test_msg = "Chào cậu, tớ là Alex, 25 tuổi."
    score, category = await semantic_engine.evaluate(test_msg, "user")
    print(f"Score: {score}, Category: {category}")
    print("CRITICAL_INFO_THRESHOLD: 0.85")
    print(f"Is CRITICAL: {score >= 0.85}")

    print("\n--- TEST 1: CHAT BÌNH THƯỜNG ---")
    res1 = await coordinator.process_message(user_id, test_msg)
    print(f"Bot: {res1}")

    print("\n--- TEST 2: KIỂM TRA TẦNG 1 (ACTIVE MEMORY) ---")
    entries = await memory_manager.t1.storage.get_entries(user_id)
    print(f"Số lượng entries: {len(entries)}")
    for e in entries:
        print(
            f"  - Score: {e.importance_score:.4f}, Category: {e.category}, Content: {e.content[:50]}..."
        )

    print("\n--- TEST 3: KIỂM TRA TẦNG 3 (CORE MEMORY) ---")
    # Đợi 2 giây để Background Task của SmartUpdater kịp chạy gọi LLM
    await asyncio.sleep(3)

    sys_prompt = await memory_manager.t3.get_system_prompt_context(user_id)
    print(f"System Prompt T3 hiện tại:\n{sys_prompt}")

    # Kiểm tra profile trực tiếp
    profile = await memory_manager.t3.storage.get_profile(user_id)
    print(f"\nProfile JSON: {profile.model_dump_json(indent=2)}")

    await container.shutdown()


asyncio.run(main())
