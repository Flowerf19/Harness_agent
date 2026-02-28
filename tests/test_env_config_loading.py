#!/usr/bin/env python3
"""
Test script to verify configuration loading from .env file
"""

import os
import sys
import tempfile
from pathlib import Path


def test_real_env_config():
    """Test that config loads correctly from real .env file"""
    print("Testing real .env file loading...")

    # Add project root to path
    project_root = Path(__file__).parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    # Check if .env file exists
    env_path = project_root / ".env"
    if not env_path.exists():
        print("⚠️  .env file not found, skipping real config test")
        return True

    # Load the actual .env file
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=env_path)

    # Reload config module
    if "src.config.settings" in sys.modules:
        del sys.modules["src.config.settings"]
    from src.config.settings import Config

    # Test that values are loaded from .env
    assert Config.LLM_PROVIDER == "qwen", (
        f"Expected LLM_PROVIDER=qwen from .env, got {Config.LLM_PROVIDER}"
    )
    assert Config.QWEN_MODEL == "qwen3-coder-next", (
        f"Expected QWEN_MODEL=qwen3-coder-next from .env, got {Config.QWEN_MODEL}"
    )
    assert Config.SYNC_COMMANDS == "0", (
        f"Expected SYNC_COMMANDS=0 from .env, got {Config.SYNC_COMMANDS}"
    )

    # Test that API keys are loaded (but don't print them for security)
    assert Config.QWEN_API_KEY is not None, "QWEN_API_KEY should be loaded from .env"
    assert Config.DISCORD_BOT_TOKEN is not None, (
        "DISCORD_BOT_TOKEN should be loaded from .env"
    )

    print("✅ Real .env file loaded correctly")
    return True


if __name__ == "__main__":
    try:
        success = test_real_env_config()
        print(
            "\n🎉 Real config test passed!"
            if success
            else "\n❌ Real config test failed!"
        )
        sys.exit(0 if success else 1)
    except Exception as e:
        import traceback

        print(f"\n❌ Real config test failed: {e}")
        traceback.print_exc()
        sys.exit(1)
