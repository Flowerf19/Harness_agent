#!/usr/bin/env python3
"""
Debug script to check and fix episodic memory for user 726302130318868500
"""

import asyncio
import json
import os
from datetime import datetime


async def debug_user_memory():
    # Import the necessary modules
    from src.services.memory_manager import MemoryManager
    from src.services.qwen_service import (
        QwenService,  # Assuming this is the LLM service
    )

    # Initialize LLM service
    llm_service = QwenService()

    # Initialize memory manager
    memory_manager = MemoryManager(llm_service, "src/data")

    user_id = "726302130318868500"

    print(f"🔍 Checking memory status for user {user_id}")

    # Check current memory status
    status = memory_manager.get_memory_status(user_id)
    print(f"Memory status: {json.dumps(status, indent=2, default=str)}")

    # Get the episodic memory directly
    episodic_memory = memory_manager.get_episodic_memory(user_id)
    print(f"Episodic memory length: {len(episodic_memory)}")

    # Try to force update all memories
    print("\n🔄 Attempting to force update all memories...")
    await memory_manager.force_update_all_memories(user_id)

    # Check again after update
    print("\n🔍 Checking memory status after update:")
    status_after = memory_manager.get_memory_status(user_id)
    print(f"Memory status: {json.dumps(status_after, indent=2, default=str)}")

    # Get the episodic memory again
    episodic_memory_after = memory_manager.get_episodic_memory(user_id)
    print(f"Episodic memory length after update: {len(episodic_memory_after)}")

    # Print first few events if any
    if episodic_memory_after:
        print(f"\n📋 First 3 events:")
        for i, event in enumerate(episodic_memory_after[:3]):
            print(f"Event {i + 1}: {json.dumps(event, indent=2)[:200]}...")


if __name__ == "__main__":
    asyncio.run(debug_user_memory())
