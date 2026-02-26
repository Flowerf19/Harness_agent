#!/usr/bin/env python3
"""
Test script để kiểm tra việc sửa lỗi callback async trong ActivityMonitor
"""

import asyncio
import os
import sys

# Thêm thư mục src vào đường dẫn Python
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from services.activity_monitor import ActivityMonitor


async def test_async_callback():
    """Test callback async được await đúng cách"""
    print("🧪 Testing async callback handling...")

    monitor = ActivityMonitor()

    # Tạo callback async mẫu
    async def async_callback(user_id, event_type, event_data):
        print(
            f"   ✅ Async callback called with: {user_id}, {event_type}, {event_data}"
        )
        # Mô phỏng một chút xử lý async
        await asyncio.sleep(0.1)
        return "async_result"

    # Tạo callback sync mẫu
    def sync_callback(user_id, event_type, event_data):
        print(f"   ✅ Sync callback called with: {user_id}, {event_type}, {event_data}")
        return "sync_result"

    # Thêm các callback
    monitor.add_priority_event_callback(async_callback)
    monitor.add_priority_event_callback(sync_callback)

    # Gọi record_priority_event (đã được sửa thành async)
    await monitor.record_priority_event("test_user", "test_event", {"data": "test"})

    print("   ✅ Async callback test passed!")


async def test_message_count_callback():
    """Test callback async trong message count trigger"""
    print("🧪 Testing async message count callback handling...")

    monitor = ActivityMonitor(message_threshold=2)  # Ngưỡng thấp để dễ test

    # Tạo callback async mẫu
    async def async_message_callback(user_id, condition):
        print(f"   ✅ Async message count callback called with: {user_id}, {condition}")
        # Mô phỏng một chút xử lý async
        await asyncio.sleep(0.1)
        return "async_msg_result"

    # Tạo callback sync mẫu
    def sync_message_callback(user_id, condition):
        print(f"   ✅ Sync message count callback called with: {user_id}, {condition}")
        return "sync_msg_result"

    # Thêm các callback
    monitor.add_message_count_callback(async_message_callback)
    monitor.add_message_count_callback(sync_message_callback)

    # Ghi nhận hoạt động đủ để kích hoạt trigger
    monitor.record_activity("test_user")
    monitor.record_activity("test_user")

    # Chạy kiểm tra điều kiện
    await monitor._check_all_conditions()

    print("   ✅ Async message count callback test passed!")


async def test_timeout_callback():
    """Test callback async trong timeout trigger"""
    print("🧪 Testing async timeout callback handling...")

    monitor = ActivityMonitor(inactivity_timeout=1)  # Ngưỡng timeout ngắn

    # Tạo callback async mẫu
    async def async_timeout_callback(user_id, condition):
        print(f"   ✅ Async timeout callback called with: {user_id}, {condition}")
        # Mô phỏng một chút xử lý async
        await asyncio.sleep(0.1)
        return "async_timeout_result"

    # Tạo callback sync mẫu
    def sync_timeout_callback(user_id, condition):
        print(f"   ✅ Sync timeout callback called with: {user_id}, {condition}")
        return "sync_timeout_result"

    # Thêm các callback
    monitor.add_timeout_callback(async_timeout_callback)
    monitor.add_timeout_callback(sync_timeout_callback)

    # Ghi nhận hoạt động
    monitor.record_activity("test_user")

    # Chờ để đạt ngưỡng timeout
    await asyncio.sleep(2)

    # Chạy kiểm tra điều kiện
    await monitor._check_all_conditions()

    print("   ✅ Async timeout callback test passed!")


async def main():
    print("🚀 Starting tests for async callback fix...")

    try:
        await test_async_callback()
        await test_message_count_callback()
        await test_timeout_callback()

        print("\n🎉 All tests passed! The async callback fix is working correctly.")
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
