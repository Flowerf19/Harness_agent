#!/usr/bin/env python3
"""
Script để kiểm tra và gỡ lỗi cơ chế khóa trong hệ thống
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List

# Cấu hình logging
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class TestLockMechanism:
    """
    Lớp mô phỏng cơ chế khóa để kiểm tra tính đúng đắn
    """

    def __init__(self):
        self._currently_responding_to = None
        self._lock_acquired_time = None
        self._pending_messages = {}
        self.test_results = []

    def _set_conversation_lock(self, user_id: str):
        """Mô phỏng việc thiết lập khóa hội thoại"""
        logger.info(f"🔒 Setting lock for user {user_id}")
        self._currently_responding_to = user_id
        self._lock_acquired_time = datetime.now()

        # Lên lịch tự động giải phóng khóa sau 5 giây (cho mục đích kiểm tra)
        asyncio.create_task(
            self._auto_release_lock_after_timeout(user_id, timeout_seconds=5)
        )

    def _release_conversation_lock(self):
        """Mô phỏng việc giải phóng khóa hội thoại"""
        if hasattr(self, "_currently_responding_to") and self._currently_responding_to:
            current_responder = self._currently_responding_to
            logger.info(f"🔓 Releasing lock for user {current_responder}")

            self._currently_responding_to = None

            if hasattr(self, "_lock_acquired_time"):
                delattr(self, "_lock_acquired_time")

            # Xử lý tin nhắn chờ sau khi giải phóng khóa
            asyncio.create_task(self._process_any_pending_messages())

    async def _auto_release_lock_after_timeout(
        self, user_id: str, timeout_seconds: int = 30
    ):
        """Tự động giải phóng khóa sau thời gian timeout"""
        await asyncio.sleep(timeout_seconds)

        current_responder = getattr(self, "_currently_responding_to", None)
        if current_responder == user_id:
            logger.warning(
                f"⚠️ Auto-releasing lock for user {user_id} after {timeout_seconds}s timeout"
            )

            self._currently_responding_to = None
            if hasattr(self, "_lock_acquired_time"):
                delattr(self, "_lock_acquired_time")

            await self._process_any_pending_messages()

    def _is_conversation_locked(self, user_id: str) -> bool:
        """Kiểm tra xem hội thoại có bị khóa không"""
        current_responder = getattr(self, "_currently_responding_to", None)
        return current_responder is not None and current_responder != user_id

    async def _process_any_pending_messages(self):
        """Xử lý các tin nhắn đang chờ"""
        logger.info("🔄 Processing any pending messages")
        # Logic xử lý tin nhắn chờ sẽ được thêm sau

    async def simulate_normal_processing(self, user_id: str):
        """Mô phỏng xử lý tin nhắn bình thường"""
        logger.info(f"💬 Simulating normal processing for user {user_id}")

        try:
            self._set_conversation_lock(user_id)

            # Giả lập xử lý tin nhắn (mất vài giây)
            await asyncio.sleep(2)

            logger.info(f"✅ Normal processing completed for user {user_id}")

        except Exception as e:
            logger.error(f"❌ Error in normal processing: {e}")
        finally:
            # Luôn giải phóng khóa
            self._release_conversation_lock()

    async def simulate_error_processing(self, user_id: str):
        """Mô phỏng xử lý tin nhắn có lỗi"""
        logger.info(f"💥 Simulating error processing for user {user_id}")

        try:
            self._set_conversation_lock(user_id)

            # Giả lập xử lý tin nhắn (mất vài giây)
            await asyncio.sleep(1)

            # Giả lập lỗi xảy ra
            raise Exception("Simulated processing error")

        except Exception as e:
            logger.error(f"❌ Expected error occurred: {e}")
        finally:
            # Luôn giải phóng khóa ngay cả khi có lỗi
            self._release_conversation_lock()

    async def simulate_cancelled_processing(self, user_id: str):
        """Mô phỏng xử lý tin nhắn bị hủy"""
        logger.info(f"🚫 Simulating cancelled processing for user {user_id}")

        try:
            self._set_conversation_lock(user_id)

            # Giả lập xử lý tin nhắn (mất vài giây)
            await asyncio.sleep(3)

        except asyncio.CancelledError:
            logger.warning(f"⚠️ Processing was cancelled for user {user_id}")
            raise
        except Exception as e:
            logger.error(f"❌ Unexpected error: {e}")
        finally:
            # Luôn giải phóng khóa ngay cả khi bị hủy
            self._release_conversation_lock()

    async def run_tests(self):
        """Chạy các bài kiểm tra"""
        logger.info("🧪 Starting lock mechanism tests...")

        # Kiểm tra 1: Xử lý bình thường
        logger.info("\n--- Test 1: Normal processing ---")
        await self.simulate_normal_processing("user_123")

        # Kiểm tra 2: Xử lý có lỗi
        logger.info("\n--- Test 2: Error processing ---")
        await self.simulate_error_processing("user_456")

        # Kiểm tra 3: Xử lý bị hủy
        logger.info("\n--- Test 3: Cancelled processing ---")
        task = asyncio.create_task(self.simulate_cancelled_processing("user_789"))
        await asyncio.sleep(1)  # Hủy sau 1 giây
        task.cancel()

        # Kiểm tra 4: Timeout tự động
        logger.info("\n--- Test 4: Automatic timeout ---")
        self._set_conversation_lock("user_timeout")
        logger.info("Set lock, waiting for automatic timeout (5 seconds)...")
        await asyncio.sleep(6)  # Chờ hơn 5 giây để timeout xảy ra

        # Kiểm tra 5: Nhiều người dùng cùng lúc
        logger.info("\n--- Test 5: Multiple users ---")
        tasks = [
            self.simulate_normal_processing("user_A"),
            self.simulate_error_processing("user_B"),
            asyncio.sleep(0.5),  # Chờ một chút rồi bắt đầu người dùng C
            self.simulate_normal_processing("user_C"),
        ]

        await asyncio.gather(*tasks, return_exceptions=True)

        logger.info("\n✅ All tests completed!")

        # Kiểm tra trạng thái cuối cùng
        if self._currently_responding_to is None:
            logger.info("✅ No locks remain after tests - SUCCESS!")
        else:
            logger.error(
                f"❌ Lock remains for user {self._currently_responding_to} - FAILURE!"
            )


async def main():
    """Hàm chính để chạy kiểm tra"""
    tester = TestLockMechanism()
    await tester.run_tests()


if __name__ == "__main__":
    asyncio.run(main())
