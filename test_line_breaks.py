#!/usr/bin/env python3
"""
Test script to verify that line breaks are preserved in response splitting
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from cogs.llm_message import LLMMessageCog
from services.gemini_service import GeminiService
from services.ollama_service import OllamaService
from services.qwen_service import QwenService


class MockBot:
    """Mock bot for testing purposes"""

    class user:
        id = 123456789

    def __init__(self):
        self.user = MockBot.user


def test_split_functions():
    """Test the response splitting functions to ensure line breaks are preserved"""

    print("Testing response splitting functions to preserve line breaks...\n")

    # Test response with various line breaks and formatting
    test_response = """Dòng đầu tiên.
Dòng thứ hai.
Dòng thứ ba có dấu chấm hỏi?
Câu trả lời: Có chứ!
Dòng thứ tư sau dấu chấm hỏi.
Dòng trống dưới đây.

Dòng sau dòng trống.
Cuối cùng là dòng kết thúc."""

    print("Original response:")
    print(repr(test_response))
    print("\nFormatted original response:")
    print(test_response)
    print("\n" + "=" * 60 + "\n")

    # Test LLMMessage._split_response_naturally
    mock_bot = MockBot()
    llm_message = LLMMessageCog(mock_bot)

    print("1. Testing LLMMessage._split_response_naturally:")
    result = llm_message._split_response_naturally(test_response)
    print(f"Number of parts: {len(result)}")
    for i, part in enumerate(result):
        print(f"Part {i + 1}: {repr(part)}")
    print()

    # Test QwenService.split_response_into_parts
    qwen_service = QwenService()
    print("2. Testing QwenService.split_response_into_parts:")
    result = qwen_service.split_response_into_parts(test_response)
    print(f"Number of parts: {len(result)}")
    for i, part in enumerate(result):
        print(f"Part {i + 1}: {repr(part)}")
    print()

    # Test GeminiService.split_response_into_parts
    gemini_service = GeminiService()
    print("3. Testing GeminiService.split_response_into_parts:")
    result = gemini_service.split_response_into_parts(test_response)
    print(f"Number of parts: {len(result)}")
    for i, part in enumerate(result):
        print(f"Part {i + 1}: {repr(part)}")
    print()

    # Test OllamaService._split_response_naturally
    ollama_service = OllamaService()
    print("4. Testing OllamaService._split_response_naturally:")
    result = ollama_service._split_response_naturally(test_response)
    print(f"Number of parts: {len(result)}")
    for i, part in enumerate(result):
        print(f"Part {i + 1}: {repr(part)}")
    print()

    # Additional test with more complex formatting
    complex_response = """Dòng 1
Dòng 2
  - Danh sách 1
  - Danh sách 2
  
Dòng sau khoảng trống
Dòng cuối cùng."""

    print("=" * 60)
    print("Testing with more complex formatting:")
    print("Original response:")
    print(repr(complex_response))
    print("\nFormatted original response:")
    print(complex_response)
    print("\n" + "-" * 40 + "\n")

    print("LLMMessage result:")
    result = llm_message._split_response_naturally(complex_response)
    print(f"Number of parts: {len(result)}")
    for i, part in enumerate(result):
        print(f"Part {i + 1}: {repr(part)}")


if __name__ == "__main__":
    test_split_functions()
