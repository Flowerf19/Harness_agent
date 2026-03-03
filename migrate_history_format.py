#!/usr/bin/env python3
"""
Script to migrate history files from HistoryService format to ConversationManager format.

This script:
- Backs up all existing history files
- Converts messages from old format (no timestamp, role="bot") to new format (with timestamp, role="assistant")
- Keeps maximum 100 messages per user
- Handles mixed format files (some messages with timestamp, some without)
"""

import json
import logging
import os
import shutil
from datetime import datetime, timezone
from typing import Any, Dict, List

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_data_directory() -> str:
    """Get the data directory path"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(current_dir, "src", "data", "user_summaries")


def backup_file(file_path: str) -> str:
    """Create a backup of the original file"""
    backup_path = file_path + ".backup"
    shutil.copy2(file_path, backup_path)
    logger.info(f"Created backup: {backup_path}")
    return backup_path


def is_new_format(message: Dict[str, Any]) -> bool:
    """Check if message is already in new format (has timestamp)"""
    return "timestamp" in message


def convert_old_message(
    message: Dict[str, Any], index: int, total_messages: int
) -> Dict[str, Any]:
    """Convert old format message to new format"""
    # Create timestamp based on position (earlier messages get earlier timestamps)
    # We'll use current time minus some offset based on position
    current_time = datetime.now(timezone.utc)
    offset_seconds = (total_messages - index) * 2  # 2 seconds between messages
    timestamp = current_time.timestamp() - offset_seconds
    iso_timestamp = datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()

    # Convert role from "bot" to "assistant"
    role = message.get("role", "user")
    if role == "bot":
        role = "assistant"

    return {
        "role": role,
        "content": message.get("content", ""),
        "timestamp": iso_timestamp,
    }


def migrate_history_file(file_path: str) -> bool:
    """Migrate a single history file to new format"""
    try:
        # Read original file
        with open(file_path, "r", encoding="utf-8") as f:
            original_history = json.load(f)

        if not original_history:
            logger.info(f"Skipping empty file: {file_path}")
            return True

        logger.info(f"Migrating {len(original_history)} messages in {file_path}")

        # Create backup
        backup_file(file_path)

        # Process messages
        migrated_history = []
        total_messages = len(original_history)

        for i, message in enumerate(original_history):
            if is_new_format(message):
                # Already in new format, keep as is
                migrated_history.append(message)
            else:
                # Convert to new format
                converted_message = convert_old_message(message, i, total_messages)
                migrated_history.append(converted_message)

        # Keep only last 100 messages
        if len(migrated_history) > 100:
            migrated_history = migrated_history[-100:]

        # Write back to file
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(migrated_history, f, ensure_ascii=False, indent=2)

        logger.info(
            f"Successfully migrated {len(migrated_history)} messages to {file_path}"
        )
        return True

    except Exception as e:
        logger.error(f"Error migrating {file_path}: {e}")
        return False


def find_history_files(data_dir: str) -> List[str]:
    """Find all history files in the data directory"""
    history_files = []
    for filename in os.listdir(data_dir):
        if filename.endswith("_history.json"):
            history_files.append(os.path.join(data_dir, filename))
    return history_files


def main():
    """Main migration function"""
    data_dir = get_data_directory()

    if not os.path.exists(data_dir):
        logger.error(f"Data directory not found: {data_dir}")
        return

    # Find all history files
    history_files = find_history_files(data_dir)

    if not history_files:
        logger.info("No history files found to migrate")
        return

    logger.info(f"Found {len(history_files)} history files to migrate")

    # Migrate each file
    successful_migrations = 0
    failed_migrations = 0

    for file_path in history_files:
        if migrate_history_file(file_path):
            successful_migrations += 1
        else:
            failed_migrations += 1

    logger.info(
        f"Migration completed: {successful_migrations} successful, {failed_migrations} failed"
    )

    if failed_migrations > 0:
        logger.warning("Some files failed to migrate. Check logs for details.")
        logger.info(
            "To restore from backups, rename .backup files back to original names."
        )


if __name__ == "__main__":
    main()
