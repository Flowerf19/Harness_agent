# filepath: discord-bot-gemini/src/config/settings.py
import os


class Config:
    DISCORD_BOT_TOKEN = os.getenv("DISCORD_LLM_BOT_TOKEN")
    DISCORD_BOT_CLIENT_ID = os.getenv("DISCORD_LLM_BOT_CLIENT_ID")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GEMINI_API_URL = os.getenv(
        "GEMINI_API_URL", "https://generativelanguage.googleapis.com/v1beta/models"
    )
    LLM_MODEL = os.getenv("LLM_MODEL", "gemini-1.5-flash")
    SYNC_COMMANDS = os.getenv("SYNC_COMMANDS", "0")

    # LLM Provider settings
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")  # 'gemini', 'ollama', or 'qwen'
    OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:30b-a3b-instruct-2507-q4_K_M")

    # Qwen API settings
    QWEN_API_KEY = os.getenv("QWEN_API_KEY")
    QWEN_API_URL = os.getenv(
        "QWEN_API_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen-max")

    # Typing simulation settings
    ENABLE_TYPING_SIMULATION = os.getenv("ENABLE_TYPING_SIMULATION", "1") == "1"
    TYPING_SPEED_WPM = int(os.getenv("TYPING_SPEED_WPM", "250"))  # Words per minute
    MIN_TYPING_DELAY = float(
        os.getenv("MIN_TYPING_DELAY", "0.5")
    )  # Minimum delay in seconds
    MAX_TYPING_DELAY = float(
        os.getenv("MAX_TYPING_DELAY", "8.0")
    )  # Maximum delay in seconds
    PART_BREAK_DELAY = float(
        os.getenv("PART_BREAK_DELAY", "0.6")
    )  # Delay between message parts
