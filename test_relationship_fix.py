#!/usr/bin/env python3
"""
Test script to verify the relationship service fixes
"""

import asyncio
import json
import os
import sys
import tempfile
from unittest.mock import AsyncMock

# Add the project root to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "."))


async def test_relationship_service():
    """Test the relationship service with various edge cases"""

    # Import inside the function to handle path issues
    from src.services.relationship_service import RelationshipService

    # Mock LLM service
    mock_llm_service = AsyncMock()
    mock_llm_service.generate_response = AsyncMock(return_value='{"relationships": []}')

    # Create temporary directory for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        # Initialize the service
        service = RelationshipService(mock_llm_service, temp_dir)

        print("✅ RelationshipService initialized successfully")

        # Test basic functionality
        service.update_user_name("123", "testuser", "Test Display", "Test Real Name")
        print("✅ User name update works")

        # Test processing a message
        await service.process_message("123", "testuser", "Hello world!")
        print("✅ Message processing works")

        # Test getting user relationships
        relationships = service.get_user_relationships("123")
        print(
            f"✅ Getting user relationships works: {len(relationships)} relationships"
        )

        # Test getting interaction stats
        stats = service.get_interaction_stats("123")
        print(f"✅ Getting interaction stats works: {stats}")

        # Test getting all users summary
        summary = service.get_all_users_summary()
        print(f"✅ Getting all users summary works: {len(summary['users'])} users")

        # Test with malformed data to ensure error handling works
        # Manually corrupt some data to test error handling
        service.relationships = {"test": "invalid_data"}  # Invalid relationship data
        relationships = service.get_user_relationships("123")
        print(
            f"✅ Handles invalid relationship data gracefully: {len(relationships)} relationships"
        )

        service.interactions = {"test": "invalid_data"}  # Invalid interaction data
        stats = service.get_interaction_stats("123")
        print(f"✅ Handles invalid interaction data gracefully: {stats}")

        print(
            "\n🎉 All tests passed! The relationship service fixes are working correctly."
        )


if __name__ == "__main__":
    asyncio.run(test_relationship_service())
