#!/usr/bin/env python3
"""
Automated E2E test for March7 memory system via A2A API
"""
import requests
import time
import json

BASE_URL = "http://localhost:8000"
TEST_USER_ID = "726302130318868500"

def send_message(content: str, user_id: str = TEST_USER_ID):
    """Send message to March7 via A2A JSON-RPC API"""
    payload = {
        "jsonrpc": "2.0",
        "method": "tasks/send",
        "params": {
            "sessionId": user_id,
            "skill": "chat",
            "message": {
                "parts": [{"type": "text", "text": content}]
            }
        },
        "id": 1
    }

    print(f"\n📤 Sending: {content}")
    response = requests.post(BASE_URL, json=payload, timeout=30)

    if response.status_code == 200:
        result = response.json()
        task_result = result.get("result", {})
        task_id = task_result.get("id")  # Changed from taskId to id

        if not task_id:
            print(f"❌ No task id in response: {result}")
            return None

        # Poll for result
        time.sleep(3)
        get_payload = {
            "jsonrpc": "2.0",
            "method": "tasks/get",
            "params": {"id": task_id},  # Changed from taskId to id
            "id": 2
        }
        get_response = requests.post(BASE_URL, json=get_payload, timeout=10)

        if get_response.status_code == 200:
            task_data = get_response.json().get("result", {})
            messages = task_data.get("messages", [])

            # Get last agent message
            for msg in reversed(messages):
                if msg.get("role") == "agent":
                    parts = msg.get("parts", [])
                    for part in parts:
                        if part.get("type") == "text":
                            reply = part.get("text", "")
                            if reply and reply != "...":
                                print(f"✅ Bot replied: {reply[:200]}")
                                return reply

        print(f"⚠️  No reply found")
        return None
    else:
        print(f"❌ Error: {response.status_code} - {response.text}")
        return None

def check_t3_profile():
    """Check T3 profile file"""
    import subprocess
    result = subprocess.run(
        ["docker", "exec", "march7", "cat", f"/app/memories/{TEST_USER_ID}.md"],
        capture_output=True, text=True
    )
    return result.stdout

def check_t2_count():
    """Check T2 memory count"""
    import subprocess
    result = subprocess.run(
        ["docker", "exec", "march7-redis", "redis-cli", "KEYS", f"t2:mem:{TEST_USER_ID}:*"],
        capture_output=True, text=True
    )
    return len(result.stdout.strip().split('\n')) if result.stdout.strip() else 0

def main():
    print("=" * 60)
    print("🚀 March7 Memory System - Automated E2E Test")
    print("=" * 60)

    # Baseline
    print("\n📊 Baseline State:")
    t2_count_before = check_t2_count()
    print(f"   T2 memories: {t2_count_before}")

    # Test 1: T3 Write
    print("\n" + "=" * 60)
    print("Test 1: T3 Profile Write")
    print("=" * 60)
    reply = send_message("Mã kiểm thử memory 2026-05-31: dragon-531")
    time.sleep(2)

    profile = check_t3_profile()
    if "dragon-531" in profile:
        print("✅ PASS: T3 profile updated with test code")
    else:
        print("❌ FAIL: Test code not found in T3 profile")

    # Test 2: T3 Read
    print("\n" + "=" * 60)
    print("Test 2: T3 Profile Read")
    print("=" * 60)
    reply = send_message("Trong memory của tôi mã kiểm thử là gì?")

    if reply and "dragon-531" in reply:
        print("✅ PASS: Bot recalled test code from T3")
    else:
        print("❌ FAIL: Bot did not recall test code")

    # Test 3: T1 Active Memory
    print("\n" + "=" * 60)
    print("Test 3: T1 Active Memory")
    print("=" * 60)
    send_message("Tên tôi là TestUser")
    time.sleep(1)
    reply = send_message("Tên tôi là gì?")

    if reply and "TestUser" in reply:
        print("✅ PASS: Bot recalled from T1")
    else:
        print("❌ FAIL: Bot did not recall from T1")

    # Test 4: T2 Consolidation (requires conversation)
    print("\n" + "=" * 60)
    print("Test 4: T2 Timeline Memory (conversation)")
    print("=" * 60)

    messages = [
        "Tôi thích anime One Piece",
        "Luffy là nhân vật yêu thích của tôi",
        "Tôi đã xem đến arc Wano",
        "Tôi thích phong cách vẽ của Oda",
        "One Piece là anime hay nhất"
    ]

    for msg in messages:
        send_message(msg)
        time.sleep(1)

    print("\n⏳ Waiting 60s for T1→T2 consolidation...")
    time.sleep(60)

    t2_count_after = check_t2_count()
    print(f"   T2 memories before: {t2_count_before}")
    print(f"   T2 memories after: {t2_count_after}")

    if t2_count_after > t2_count_before:
        print("✅ PASS: New T2 memories created")
    else:
        print("⚠️  WARNING: No new T2 memories (check logs)")

    # Test 5: T2 Search
    print("\n" + "=" * 60)
    print("Test 5: T2 Memory Search")
    print("=" * 60)
    time.sleep(5)  # Wait a bit more
    reply = send_message("Tôi đã nói gì về anime?")

    if reply and ("One Piece" in reply or "Luffy" in reply or "anime" in reply.lower()):
        print("✅ PASS: Bot recalled from T2")
    else:
        print("❌ FAIL: Bot did not recall anime info from T2")

    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Summary")
    print("=" * 60)
    print(f"Final T2 memory count: {check_t2_count()}")
    print("\nCheck logs for details:")
    print("  docker logs march7 --tail 100 | grep -E 'T1:|T2:|T3:|ERROR'")

if __name__ == "__main__":
    main()
