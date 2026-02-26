#!/usr/bin/env python3
"""
Simple debug script to check episodic memory for user 726302130318868500
"""

import json
import os


def debug_user_memory():
    user_id = "726302130318868500"
    data_dir = "src/data"

    print(f"🔍 Checking memory files for user {user_id}")

    # Check if history file exists
    history_file = os.path.join(data_dir, "user_summaries", f"{user_id}_history.json")
    if os.path.exists(history_file):
        with open(history_file, "r", encoding="utf-8") as f:
            history = json.load(f)
        print(f"✅ History file exists with {len(history)} entries")
    else:
        print(f"❌ History file does not exist: {history_file}")

    # Check if episodic memory file exists
    episodic_file = os.path.join(data_dir, "user_summaries", f"{user_id}_episodic.json")
    if os.path.exists(episodic_file):
        with open(episodic_file, "r", encoding="utf-8") as f:
            episodic = json.load(f)
        print(f"✅ Episodic memory file exists with {len(episodic)} events")

        # Print first few events
        if episodic:
            print(f"\n📋 First 3 events:")
            for i, event in enumerate(episodic[:3]):
                print(f"Event {i + 1}: {json.dumps(event, indent=2)[:200]}...")
    else:
        print(f"❌ Episodic memory file does not exist: {episodic_file}")

    # Check if summary file exists
    summary_file = os.path.join(data_dir, "user_summaries", f"{user_id}_summary.txt")
    if os.path.exists(summary_file):
        with open(summary_file, "r", encoding="utf-8") as f:
            summary = f.read()
        print(f"✅ Summary file exists with {len(summary)} characters")
    else:
        print(f"❌ Summary file does not exist: {summary_file}")


if __name__ == "__main__":
    debug_user_memory()
