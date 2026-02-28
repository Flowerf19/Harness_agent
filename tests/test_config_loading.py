#!/usr/bin/env python3
"""
Test script to verify configuration loading and compatibility
"""

import importlib
import os
import sys


def reload_config_module():
    """Reload the config module to pick up new environment variables"""
    if "src.config.settings" in sys.modules:
        del sys.modules["src.config.settings"]
    from src.config.settings import Config

    return Config


def test_config_defaults():
    """Test that default values are loaded correctly"""
    print("Testing default values...")
    # Clear environment and reload config
    original_env = dict(os.environ)
    try:
        # Clear relevant env vars
        for key in list(os.environ.keys()):
            if key.startswith(
                (
                    "DISCORD_",
                    "GEMINI_",
                    "LLM_",
                    "OLLAMA_",
                    "QWEN_",
                    "LM_STUDIO_",
                    "ENABLE_TYPING",
                    "TYPING_",
                    "LOG_",
                    "MAX_MESSAGES",
                )
            ):
                del os.environ[key]

        Config = reload_config_module()

        # Test default values
        assert (
            Config.GEMINI_API_URL
            == "https://generativelanguage.googleapis.com/v1beta/models"
        ), f"Expected default GEMINI_API_URL, got {Config.GEMINI_API_URL}"
        assert Config.LLM_MODEL == "gemini-1.5-flash", (
            f"Expected default LLM_MODEL, got {Config.LLM_MODEL}"
        )
        assert Config.SYNC_COMMANDS == "0", (
            f"Expected default SYNC_COMMANDS, got {Config.SYNC_COMMANDS}"
        )
        assert Config.LLM_PROVIDER == "gemini", (
            f"Expected default LLM_PROVIDER, got {Config.LLM_PROVIDER}"
        )
        assert Config.OLLAMA_API_URL == "http://localhost:11434", (
            f"Expected default OLLAMA_API_URL, got {Config.OLLAMA_API_URL}"
        )
        assert Config.OLLAMA_MODEL == "qwen3:30b-a3b-instruct-2507-q4_K_M", (
            f"Expected default OLLAMA_MODEL, got {Config.OLLAMA_MODEL}"
        )
        assert (
            Config.QWEN_API_URL == "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ), f"Expected default QWEN_API_URL, got {Config.QWEN_API_URL}"
        assert Config.QWEN_MODEL == "qwen-max", (
            f"Expected default QWEN_MODEL, got {Config.QWEN_MODEL}"
        )
        assert Config.ENABLE_TYPING_SIMULATION == True, (
            f"Expected default ENABLE_TYPING_SIMULATION, got {Config.ENABLE_TYPING_SIMULATION}"
        )
        assert Config.TYPING_SPEED_WPM == 250, (
            f"Expected default TYPING_SPEED_WPM, got {Config.TYPING_SPEED_WPM}"
        )
        assert Config.MIN_TYPING_DELAY == 0.5, (
            f"Expected default MIN_TYPING_DELAY, got {Config.MIN_TYPING_DELAY}"
        )
        assert Config.MAX_TYPING_DELAY == 8.0, (
            f"Expected default MAX_TYPING_DELAY, got {Config.MAX_TYPING_DELAY}"
        )
        assert Config.PART_BREAK_DELAY == 0.6, (
            f"Expected default PART_BREAK_DELAY, got {Config.PART_BREAK_DELAY}"
        )
        assert Config.LLM_TEMPERATURE == 0.7, (
            f"Expected default LLM_TEMPERATURE, got {Config.LLM_TEMPERATURE}"
        )
        assert Config.LLM_MAX_TOKENS == 100, (
            f"Expected default LLM_MAX_TOKENS, got {Config.LLM_MAX_TOKENS}"
        )
        assert Config.LLM_TOP_P == 0.9, (
            f"Expected default LLM_TOP_P, got {Config.LLM_TOP_P}"
        )
        assert Config.LLM_TOP_K == 40, (
            f"Expected default LLM_TOP_K, got {Config.LLM_TOP_K}"
        )
        assert Config.LM_STUDIO_API_URL == "http://localhost:1234", (
            f"Expected default LM_STUDIO_API_URL, got {Config.LM_STUDIO_API_URL}"
        )
        assert Config.LM_STUDIO_MODEL == "local-model", (
            f"Expected default LM_STUDIO_MODEL, got {Config.LM_STUDIO_MODEL}"
        )
        assert Config.LOG_LEVEL == "INFO", (
            f"Expected default LOG_LEVEL, got {Config.LOG_LEVEL}"
        )
        assert Config.MAX_MESSAGES == 500, (
            f"Expected default MAX_MESSAGES, got {Config.MAX_MESSAGES}"
        )

        print("✅ All default values loaded correctly")
    finally:
        # Restore original environment
        os.environ.clear()
        os.environ.update(original_env)


def test_config_env_override():
    """Test that environment variables override defaults"""
    print("Testing environment variable overrides...")
    original_env = dict(os.environ)
    try:
        # Set test environment variables
        test_env = {
            "GEMINI_API_URL": "https://test-api.com",
            "LLM_MODEL": "test-model",
            "LLM_PROVIDER": "ollama",
            "OLLAMA_API_URL": "http://test:1234",
            "ENABLE_TYPING_SIMULATION": "0",
            "TYPING_SPEED_WPM": "300",
            "LLM_TEMPERATURE": "0.5",
            "LOG_LEVEL": "DEBUG",
        }
        os.environ.update(test_env)

        Config = reload_config_module()

        assert Config.GEMINI_API_URL == "https://test-api.com", (
            f"Expected GEMINI_API_URL from env, got {Config.GEMINI_API_URL}"
        )
        assert Config.LLM_MODEL == "test-model", (
            f"Expected LLM_MODEL from env, got {Config.LLM_MODEL}"
        )
        assert Config.LLM_PROVIDER == "ollama", (
            f"Expected LLM_PROVIDER from env, got {Config.LLM_PROVIDER}"
        )
        assert Config.OLLAMA_API_URL == "http://test:1234", (
            f"Expected OLLAMA_API_URL from env, got {Config.OLLAMA_API_URL}"
        )
        assert Config.ENABLE_TYPING_SIMULATION == False, (
            f"Expected ENABLE_TYPING_SIMULATION from env, got {Config.ENABLE_TYPING_SIMULATION}"
        )
        assert Config.TYPING_SPEED_WPM == 300, (
            f"Expected TYPING_SPEED_WPM from env, got {Config.TYPING_SPEED_WPM}"
        )
        assert Config.LLM_TEMPERATURE == 0.5, (
            f"Expected LLM_TEMPERATURE from env, got {Config.LLM_TEMPERATURE}"
        )
        assert Config.LOG_LEVEL == "DEBUG", (
            f"Expected LOG_LEVEL from env, got {Config.LOG_LEVEL}"
        )

        print("✅ Environment variables override defaults correctly")
    finally:
        # Restore original environment
        os.environ.clear()
        os.environ.update(original_env)


def test_config_type_conversion():
    """Test that type conversion works correctly"""
    print("Testing type conversion...")
    original_env = dict(os.environ)
    try:
        # Set test environment variables with string values
        test_env = {
            "TYPING_SPEED_WPM": "400",
            "MIN_TYPING_DELAY": "1.0",
            "MAX_TYPING_DELAY": "10.0",
            "LLM_MAX_TOKENS": "150",
            "LLM_TOP_K": "50",
        }
        os.environ.update(test_env)

        Config = reload_config_module()

        # Check types and values
        assert isinstance(Config.TYPING_SPEED_WPM, int), (
            f"TYPING_SPEED_WPM should be int, got {type(Config.TYPING_SPEED_WPM)}"
        )
        assert isinstance(Config.MIN_TYPING_DELAY, float), (
            f"MIN_TYPING_DELAY should be float, got {type(Config.MIN_TYPING_DELAY)}"
        )
        assert isinstance(Config.MAX_TYPING_DELAY, float), (
            f"MAX_TYPING_DELAY should be float, got {type(Config.MAX_TYPING_DELAY)}"
        )
        assert isinstance(Config.LLM_MAX_TOKENS, int), (
            f"LLM_MAX_TOKENS should be int, got {type(Config.LLM_MAX_TOKENS)}"
        )
        assert isinstance(Config.LLM_TOP_K, int), (
            f"LLM_TOP_K should be int, got {type(Config.LLM_TOP_K)}"
        )

        assert Config.TYPING_SPEED_WPM == 400, (
            f"Expected TYPING_SPEED_WPM=400, got {Config.TYPING_SPEED_WPM}"
        )
        assert Config.MIN_TYPING_DELAY == 1.0, (
            f"Expected MIN_TYPING_DELAY=1.0, got {Config.MIN_TYPING_DELAY}"
        )
        assert Config.MAX_TYPING_DELAY == 10.0, (
            f"Expected MAX_TYPING_DELAY=10.0, got {Config.MAX_TYPING_DELAY}"
        )
        assert Config.LLM_MAX_TOKENS == 150, (
            f"Expected LLM_MAX_TOKENS=150, got {Config.LLM_MAX_TOKENS}"
        )
        assert Config.LLM_TOP_K == 50, f"Expected LLM_TOP_K=50, got {Config.LLM_TOP_K}"

        print("✅ Type conversion works correctly")
    finally:
        # Restore original environment
        os.environ.clear()
        os.environ.update(original_env)


def main():
    """Run all tests"""
    print("🧪 Testing configuration loading and compatibility...\n")

    # Add project root to path
    project_root = os.path.dirname(os.path.abspath(__file__))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    try:
        test_config_defaults()
        print()
        test_config_env_override()
        print()
        test_config_type_conversion()

        print("\n🎉 All tests passed! Configuration system is working correctly.")
        return True
    except Exception as e:
        import traceback

        print(f"\n❌ Test failed: {e}")
        print("Full traceback:")
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
