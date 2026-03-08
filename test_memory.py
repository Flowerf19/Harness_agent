import asyncio

from dotenv import load_dotenv

# Load .env TRƯỚC khi import các module khác
load_dotenv()

from src.services.dependencies import AppContainer  # noqa: E402


async def main():
    # 1. Kích hoạt Trạm điện
    container = AppContainer.get_instance()
    await container.initialize()

    coordinator = container.chat_coordinator
    user_id = "test_user_123"

    print("\n--- TEST 1: CHAT BÌNH THƯỜNG ---")
    res1 = await coordinator.process_message(user_id, "Chào cậu, tớ là Alex, 25 tuổi.")
    print(f"Bot: {res1}")

    print("\n--- TEST 2: KIỂM TRA TẦNG 3 (CORE MEMORY) ĐÃ CẬP NHẬT CHƯA ---")
    # Đợi 2 giây để Background Task của SmartUpdater kịp chạy gọi LLM
    await asyncio.sleep(2)

    sys_prompt = await container.memory_manager.t3.get_system_prompt_context(user_id)
    print(f"System Prompt T3 hiện tại:\n{sys_prompt}")
    # KỲ VỌNG: System prompt phải in ra được "Danh xưng: Alex | Tuổi: 25"

    await container.shutdown()


asyncio.run(main())
