#!/usr/bin/env python3
"""
Test script to verify the fix for JSON parsing in extract_relationship_info function
"""

import asyncio
import os
import sys
from datetime import datetime

# Add project root to path for importing services
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)


# Mock LLM service for testing
class MockLLMService:
    async def generate_response(self, prompt: str, context: str = None):
        # Simulate different types of LLM responses
        if "test_valid_json" in prompt:
            return '{"relationships": [{"person1": "Alice", "person2": "Bob", "relationship_type": "friend", "confidence": 0.9, "context": "They are friends"}]}'
        elif "test_invalid_json" in prompt:
            return 'Some text before {"relationships": [{"person1": "Alice", "person2": "Bob", "relationship_type": "friend", "confidence": 0.9, "context": "They are friends"}]} Some text after'
        elif "test_malformed_json" in prompt:
            return 'Some text before {"relationships": [{"person1": "Alice", "person2": "Bob", "relationship_type": "friend", "confidence": 0.9, "context": "They are friends",}]} Some text after'
        elif "test_no_json" in prompt:
            return "This is just plain text with no JSON"
        elif "test_partial_json" in prompt:
            return 'Here is the relationships: [{"person1": "Alice", "person2": "Bob", "relationship_type": "friend"}]'
        elif "test_nested_json" in prompt:
            return 'Text before {"meta": {"info": "some info"}, "relationships": [{"person1": "Alice", "person2": "Bob", "relationship_type": "friend", "confidence": 0.9, "context": "They are friends"}]} Text after'
        else:
            return '{"relationships": []}'


class MockLogger:
    def error(self, msg):
        print(f"ERROR: {msg}")

    def warning(self, msg):
        print(f"WARNING: {msg}")

    def debug(self, msg):
        print(f"DEBUG: {msg}")


# Copy the fixed extract_relationship_info logic for testing
async def test_extract_relationship_info(
    message_content: str, author_id: str, llm_service
):
    """Test version of the fixed extract_relationship_info function"""
    logger = MockLogger()

    try:
        # Create a prompt for the LLM to analyze relationships in the message
        prompt = f"""test_{message_content}

TIN NHẮN: {message_content}

Hãy xác định các cặp người dùng và mối quan hệ giữa họ. Trả lời theo định dạng JSON như sau:
{{
  "relationships": [
    {{
      "person1": "tên người 1",
      "person2": "tên người 2", 
      "relationship_type": "friend|crush|dislike|romantic|dating|ex|unknown",
      "confidence": 0.0-1.0,
      "context": "ngữ cảnh xác định mối quan hệ"
    }}
  ]
}}

Chỉ trả lời dưới dạng JSON, không giải thích thêm:"""

        # Call the LLM to analyze relationships
        llm_response = await llm_service.generate_response(prompt)

        # Parse the LLM response as JSON
        import json
        import re

        # First, try to parse the entire response as JSON
        try:
            response_json = json.loads(llm_response)
        except json.JSONDecodeError:
            # If that fails, try to extract JSON from the response
            # Look for JSON between curly braces, handling nested objects
            # Using a more robust approach to find JSON objects

            # Find the first complete JSON object by tracking braces
            start_pos = llm_response.find("{")
            if start_pos != -1:
                brace_count = 0
                for i, char in enumerate(llm_response[start_pos:], start=start_pos):
                    if char == "{":
                        brace_count += 1
                    elif char == "}":
                        brace_count -= 1
                        if brace_count == 0:
                            json_str = llm_response[start_pos : i + 1]
                            try:
                                response_json = json.loads(json_str)
                                break
                            except json.JSONDecodeError:
                                # If this JSON string fails, try to clean it up
                                # Remove potential trailing commas before closing braces/brackets
                                cleaned_json = re.sub(r",(\s*[}\]])", r"\1", json_str)
                                try:
                                    response_json = json.loads(cleaned_json)
                                    break
                                except json.JSONDecodeError:
                                    # Try to find smaller JSON objects within the response
                                    # Look for relationships array specifically
                                    rel_pattern = r'"relationships"\s*:\s*\[(?:[^[\]]|\[(?:[^[\]]|\[[^[\]]*\])*\])*\]'
                                    rel_match = re.search(
                                        rel_pattern, llm_response, re.DOTALL
                                    )
                                    if rel_match:
                                        # Extract the relationships part and wrap it in a basic object
                                        rel_content = rel_match.group()
                                        temp_json_str = "{" + rel_content + "}"
                                        try:
                                            response_json = json.loads(temp_json_str)
                                            break
                                        except json.JSONDecodeError:
                                            # If all parsing attempts fail, return empty result
                                            response_json = {"relationships": []}
                                    else:
                                        # If still no JSON found, return empty result
                                        response_json = {"relationships": []}
            else:
                # If no opening brace found, return empty result
                response_json = {"relationships": []}

        relationships_found = []

        # Validate that response_json has the expected structure
        if not isinstance(response_json, dict):
            logger.warning("LLM response is not a dictionary, using fallback")
            return []

        relationships_data = response_json.get("relationships", [])

        # Validate that relationships_data is a list
        if not isinstance(relationships_data, list):
            logger.warning(
                "LLM response 'relationships' field is not a list, using fallback"
            )
            return []

        for rel_data in relationships_data:
            # Validate that rel_data is a dictionary and has required fields
            if not isinstance(rel_data, dict):
                logger.warning(f"Skipping non-dictionary relationship data: {rel_data}")
                continue

            if (
                "person1" in rel_data
                and "person2" in rel_data
                and "relationship_type" in rel_data
            ):
                # Validate that the required fields are strings
                person1 = rel_data.get("person1")
                person2 = rel_data.get("person2")
                relationship_type = rel_data.get("relationship_type")

                if not all(
                    isinstance(field, str)
                    for field in [person1, person2, relationship_type]
                ):
                    logger.warning(
                        f"Skipping relationship with invalid field types: {rel_data}"
                    )
                    continue

                relationships_found.append(
                    {
                        "person1": person1.strip(),
                        "person2": person2.strip(),
                        "relationship_type": relationship_type,
                        "reported_by": author_id,
                        "timestamp": datetime.now().isoformat(),
                        "context": rel_data.get("context", ""),
                        "confidence": rel_data.get(
                            "confidence", 0.7
                        ),  # Default confidence if not provided
                    }
                )
            else:
                logger.debug(
                    f"Skipping relationship data missing required fields: {rel_data}"
                )

        return relationships_found

    except json.JSONDecodeError:
        logger.error(
            "Failed to parse LLM response as JSON in extract_relationship_info"
        )
        # In a real scenario, we'd call the fallback, but for testing return empty
        return []
    except Exception as e:
        logger.error(f"Error extracting relationship info with LLM: {e}")
        # In a real scenario, we'd call the fallback, but for testing return empty
        return []


async def run_tests():
    """Run tests to verify the fix works correctly"""
    llm_service = MockLLMService()

    print("Testing the fixed JSON parsing logic...\n")

    # Test 1: Valid JSON
    print("Test 1: Valid JSON")
    result = await test_extract_relationship_info("valid_json", "12345", llm_service)
    print(f"Result: {result}")
    print(f"Expected: 1 relationship, Got: {len(result)} relationships\n")

    # Test 2: JSON with extra text around it
    print("Test 2: JSON with extra text")
    result = await test_extract_relationship_info("invalid_json", "12345", llm_service)
    print(f"Result: {result}")
    print(f"Expected: 1 relationship, Got: {len(result)} relationships\n")

    # Test 3: Malformed JSON (trailing comma)
    print("Test 3: Malformed JSON with trailing comma")
    result = await test_extract_relationship_info(
        "malformed_json", "12345", llm_service
    )
    print(f"Result: {result}")
    print(
        f"Expected: 1 relationship (after cleaning), Got: {len(result)} relationships\n"
    )

    # Test 4: No JSON in response
    print("Test 4: No JSON in response")
    result = await test_extract_relationship_info("no_json", "12345", llm_service)
    print(f"Result: {result}")
    print(f"Expected: 0 relationships, Got: {len(result)} relationships\n")

    # Test 5: Nested JSON
    print("Test 5: Nested JSON")
    result = await test_extract_relationship_info("nested_json", "12345", llm_service)
    print(f"Result: {result}")
    print(f"Expected: 1 relationship, Got: {len(result)} relationships\n")

    print("All tests completed!")


if __name__ == "__main__":
    asyncio.run(run_tests())
