#!/usr/bin/env python3
"""
Script kiểm thử tính năng cập nhật episodic memory sau khi sửa lỗi
"""

import asyncio
import json
import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock


# Mock các thành phần phụ thuộc
class MockLLMService:
    def __init__(self):
        self.responses = {
            "valid_json": '{"events": [{"type": "fact", "category": "personal_info", "summary": "Test event", "details": "Test details", "timestamp": "2026-02-26T17:00:00", "confidence": 0.8}], "key_themes": ["test"], "important_facts": ["test"]}',
            "invalid_json": "This is not a JSON response",
            "partial_json": '{"events": [{"type": "fact", "category": "personal_info", "summary": "Test event", "details": "Test details", "timestamp": "2026-02-26T17:00:00", "confidence": 0.8}]',
            "empty_response": "",
            "malformed_json": '{"events": [{"type": "fact", "category": "personal_info", "summary": "Test event", "details": "Test details", "timestamp": "2026-02-26T17:00:00", "confidence": 0.8},], "key_themes": ["test"], "important_facts": ["test"]}',
        }

    async def generate_response(self, prompt, session_id):
        # Trả về các loại phản hồi khác nhau để kiểm thử
        if "test_valid" in session_id:
            return self.responses["valid_json"]
        elif "test_invalid" in session_id:
            return self.responses["invalid_json"]
        elif "test_partial" in session_id:
            return self.responses["partial_json"]
        elif "test_empty" in session_id:
            return self.responses["empty_response"]
        elif "test_malformed" in session_id:
            return self.responses["malformed_json"]
        else:
            # Trả về JSON hợp lệ mặc định
            return self.responses["valid_json"]


async def test_memory_background_service():
    """
    Kiểm thử MemoryBackgroundService với các trường hợp khác nhau
    """
    print("🧪 Bắt đầu kiểm thử MemoryBackgroundService...")

    # Import sau khi mock các thành phần cần thiết
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

    # Import và mock các module cần thiết
    from services.memory_background_service import MemoryBackgroundService

    # Tạo mock cho các thành phần phụ thuộc
    llm_service = MockLLMService()
    data_dir = "./test_data"

    # Tạo thư mục test nếu chưa tồn tại
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(os.path.join(data_dir, "user_summaries"), exist_ok=True)

    # Tạo instance của MemoryBackgroundService
    service = MemoryBackgroundService(llm_service, data_dir)

    # Test các trường hợp khác nhau
    test_cases = [
        ("test_valid", "JSON hợp lệ"),
        ("test_invalid", "JSON không hợp lệ"),
        ("test_partial", "JSON không đầy đủ"),
        ("test_empty", "Phản hồi trống"),
        ("test_malformed", "JSON sai cú pháp"),
    ]

    for session_id, description in test_cases:
        print(f"\n📋 Kiểm thử: {description}")
        print(f"Session ID: {session_id}")

        # Mock phương thức _get_user_history để trả về dữ liệu giả lập
        service._get_user_history = MagicMock(
            return_value=[
                {
                    "role": "user",
                    "content": "Hello",
                    "timestamp": "2026-02-26T17:00:00",
                },
                {
                    "role": "assistant",
                    "content": "Hi there!",
                    "timestamp": "2026-02-26T17:00:01",
                },
            ]
        )

        # Mock phương thức _append_to_episodic_memory
        service._append_to_episodic_memory = AsyncMock()

        # Mock phương thức _cleanup_working_memory
        service._cleanup_working_memory = AsyncMock()

        try:
            # Gọi phương thức _update_episodic_memory
            await service._update_episodic_memory("test_user_123")
            print("✅ Cập nhật thành công")
        except Exception as e:
            print(f"❌ Lỗi: {str(e)}")

    print("\n🎯 Kiểm thử hoàn tất!")

    # Dọn dẹp
    import shutil

    if os.path.exists(data_dir):
        shutil.rmtree(data_dir)


def test_parse_llm_extraction_result():
    """
    Kiểm thử riêng phương thức _parse_llm_extraction_result
    """
    print("\n🧪 Kiểm thử phương thức _parse_llm_extraction_result...")

    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

    from services.memory_background_service import MemoryBackgroundService

    # Tạo instance để truy cập phương thức
    service = MemoryBackgroundService(None, "./test")

    test_responses = [
        (
            '{"events": [{"type": "fact", "category": "personal_info", "summary": "Test", "details": "Details", "timestamp": "2026-02-26T17:00:00", "confidence": 0.8}], "key_themes": ["test"], "important_facts": ["test"]}',
            "JSON hợp lệ",
        ),
        ("This is not a JSON response", "Không phải JSON"),
        (
            '{"events": [{"type": "fact", "category": "personal_info", "summary": "Test", "details": "Details", "timestamp": "2026-02-26T17:00:00", "confidence": 0.8}]',
            "JSON không đầy đủ",
        ),
        ("", "Phản hồi trống"),
        (
            '{"events": [{"type": "fact", "category": "personal_info", "summary": "Test", "details": "Details", "timestamp": "2026-02-26T17:00:00", "confidence": 0.8},], "key_themes": ["test"]}',
            "JSON sai cú pháp",
        ),
    ]

    for response, description in test_responses:
        print(f"\n📋 Kiểm thử: {description}")
        print(f"Input: {response[:50]}{'...' if len(response) > 50 else ''}")

        result = service._parse_llm_extraction_result(response)
        print(f"Output: {result}")

        if result and "events" in result:
            print(f"✅ Có {len(result['events'])} sự kiện được trích xuất")
        else:
            print("⚠️ Không có sự kiện nào được trích xuất")


if __name__ == "__main__":
    print("🚀 Bắt đầu kiểm thử tính năng sửa lỗi episodic memory...")

    # Kiểm thử phương thức parse
    test_parse_llm_extraction_result()

    # Kiểm thử toàn bộ dịch vụ
    asyncio.run(test_memory_background_service())

    print("\n✅ Tất cả kiểm thử đã hoàn tất!")
