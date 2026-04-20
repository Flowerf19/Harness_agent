# filepath: discord-bot-gemini/src/config/settings.py
import os


class Config:
    DISCORD_BOT_TOKEN = os.getenv("DISCORD_LLM_BOT_TOKEN")
    DISCORD_BOT_CLIENT_ID = os.getenv("DISCORD_LLM_BOT_CLIENT_ID")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GEMINI_API_URL = os.getenv(
        "GEMINI_API_URL", "https://generativelanguage.googleapis.com/v1beta/models"
    )
    LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash")
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

    # LLM Generation parameters
    LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    # [REASONING MODELS] Tăng max_tokens vì reasoning models cần tokens cho thinking + final answer
    # Model thường: 100-500 tokens đủ
    # Reasoning models (DeepSeek R1, Qwen thinking): cần 500-2000 tokens
    LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "2000"))
    LLM_TOP_P = float(os.getenv("LLM_TOP_P", "0.9"))
    LLM_TOP_K = int(os.getenv("LLM_TOP_K", "40"))

    # LM Studio settings
    LM_STUDIO_API_URL = os.getenv("LM_STUDIO_API_URL", "http://localhost:1234")
    LM_STUDIO_MODEL = os.getenv("LM_STUDIO_MODEL", "local-model")

    # Logging configuration
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    # Message limit configuration
    MAX_MESSAGES = int(os.getenv("MAX_MESSAGES", "500"))

    # LangSmith Tracing configuration
    LANGCHAIN_API_KEY = os.getenv("LANGCHAIN_API_KEY")
    LANGCHAIN_TRACING_V2 = os.getenv("LANGCHAIN_TRACING_V2", "true").lower() == "true"
    LANGCHAIN_PROJECT = os.getenv("LANGCHAIN_PROJECT", "discord-bot")
    LANGCHAIN_ENDPOINT = os.getenv(
        "LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com"
    )

    # Redis configuration for Active Memory (Tier 1) storage
    REDIS_ENABLED = os.getenv("REDIS_ENABLED", "false").lower() == "true"
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
    REDIS_DB = int(os.getenv("REDIS_DB", "0"))

    # Qdrant configuration for Episodic Memory (Tier 2) storage
    QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
    QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", None)
    QDRANT_COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_NAME", "episodic_memory")

    # Tavily API configuration for Web Search
    TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", None)
    TAVILY_API_URL = os.getenv("TAVILY_API_URL", "https://api.tavily.com")
    TAVILY_MAX_RESULTS = int(os.getenv("TAVILY_MAX_RESULTS", "5"))
    TAVILY_SEARCH_DEPTH = os.getenv("TAVILY_SEARCH_DEPTH", "basic")
    TAVILY_TIMEOUT = int(os.getenv("TAVILY_TIMEOUT", "30"))
