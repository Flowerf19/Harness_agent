import asyncio
import os
import sys

# Thêm đường dẫn để import twin
sys.path.insert(0, os.path.abspath('.'))

from twin.shared.memory.consolidation_client import ConsolidationClient

async def main():
    print("Testing A2A Consolidation Client to Evernight...")
    # Khởi tạo client gọi tới port 8001
    client = ConsolidationClient(evernight_url="http://localhost:8001")
    
    result = await client.consolidate_scope(
        scope="user",
        scope_id="1234567890", # Test user ID
        reason="manual_test"
    )
    print("Result:", result)
    await client.close()

if __name__ == "__main__":
    asyncio.run(main())
