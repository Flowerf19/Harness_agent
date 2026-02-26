#!/usr/bin/env python3
"""
Script to force update episodic memory for user 726302130318868500
"""

import json
import os
from datetime import datetime


def force_update_episodic_memory(user_id: str, data_dir: str):
    """
    Manually create episodic memory from existing history
    """
    history_file = os.path.join(data_dir, "user_summaries", f"{user_id}_history.json")
    episodic_file = os.path.join(data_dir, "user_summaries", f"{user_id}_episodic.json")

    # Check if history file exists
    if not os.path.exists(history_file):
        print(f"❌ History file does not exist: {history_file}")
        return False

    # Load history
    with open(history_file, "r", encoding="utf-8") as f:
        history = json.load(f)

    print(f"✅ Loaded {len(history)} messages from history")

    # Process history to extract important events
    events = []

    # Group messages by conversation sessions (separated by time gaps)
    for i, msg in enumerate(history):
        if msg.get("role") == "user":
            # Simple heuristic: capture user statements that seem significant
            content = msg.get("content", "").lower().strip()

            # Look for potential facts, preferences, or important statements
            if any(
                keyword in content
                for keyword in [
                    "tên",
                    "name",
                    "tuổi",
                    "age",
                    "thích",
                    "like",
                    "love",
                    "muốn",
                    "want",
                    "plan",
                    "work",
                    "job",
                    "code",
                    "programming",
                ]
            ):
                event = {
                    "type": "fact",
                    "category": "personal_info",
                    "summary": f"User mentioned: {msg.get('content', '')[:50]}...",
                    "details": msg.get("content"),
                    "timestamp": msg.get("timestamp", datetime.now().isoformat()),
                    "confidence": 0.8,
                }
                events.append(event)

            # Capture all interactions as general events
            event = {
                "type": "interaction",
                "category": "conversation",
                "summary": f"Conversation: {msg.get('content', '')[:50]}...",
                "details": msg.get("content"),
                "timestamp": msg.get("timestamp", datetime.now().isoformat()),
                "confidence": 0.6,
            }
            events.append(event)

    # Also add assistant responses that might contain important information
    for i, msg in enumerate(history):
        if msg.get("role") == "assistant":
            content = msg.get("content", "").lower().strip()
            if len(content) > 20:  # Non-trivial responses
                event = {
                    "type": "response",
                    "category": "interaction",
                    "summary": f"Assistant responded: {msg.get('content', '')[:50]}...",
                    "details": msg.get("content"),
                    "timestamp": msg.get("timestamp", datetime.now().isoformat()),
                    "confidence": 0.5,
                }
                events.append(event)

    print(f"✅ Extracted {len(events)} events from history")

    # Load existing events if file exists
    existing_events = []
    if os.path.exists(episodic_file):
        try:
            with open(episodic_file, "r", encoding="utf-8") as f:
                existing_events = json.load(f)
                if not isinstance(existing_events, list):
                    existing_events = []
        except Exception as e:
            print(f"⚠️ Error loading existing episodic memory: {e}")
            existing_events = []

    # Combine with existing events
    all_events = existing_events + events

    # Limit to last 200 events to prevent file from growing too large
    if len(all_events) > 200:
        all_events = all_events[-200:]

    # Add metadata
    for event in all_events:
        if "added_at" not in event:
            event["added_at"] = datetime.now().isoformat()

    # Save to episodic memory file
    with open(episodic_file, "w", encoding="utf-8") as f:
        json.dump(all_events, f, ensure_ascii=False, indent=2)

    print(
        f"✅ Saved {len(all_events)} total events to episodic memory: {episodic_file}"
    )

    # Show sample of events
    print(f"\n📋 Sample of first 3 events:")
    for i, event in enumerate(all_events[:3]):
        print(f"Event {i + 1}: {event['summary']}")

    return True


if __name__ == "__main__":
    user_id = "726302130318868500"
    data_dir = "src/data"

    print(f"🔄 Forcing episodic memory update for user {user_id}")

    success = force_update_episodic_memory(user_id, data_dir)

    if success:
        print(f"✅ Episodic memory update completed successfully!")
    else:
        print(f"❌ Episodic memory update failed!")
