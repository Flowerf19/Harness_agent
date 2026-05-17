# filepath: discord-bot-gemini/src/config/settings.py
import os


class Config:
    DISCORD_BOT_TOKEN = os.getenv("DISCORD_MARCH7_TOKEN")
    DISCORD_BOT_CLIENT_ID = os.getenv("DISCORD_MARCH7_CLIENT_ID")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GEMINI_API_URL = os.getenv("GEMINI_API_URL", "https://generativelanguage.googleapis.com/v1beta/models")
    LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash")
    SYNC_COMMANDS = os.getenv("SYNC_COMMANDS", "0")

    # LLM Provider settings
    # Only two providers are supported at runtime:
    # - gemini: GeminiService (Gemini protocol)
    # - openai / openai_compat: OpenAIService (OpenAI-compatible /chat/completions)
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")
    OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:30b-a3b-instruct-2507-q4_K_M")

    # Generic OpenAI-compatible API settings
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "dummy-key")
    OPENAI_API_URL = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", os.getenv("LLM_MODEL", "gpt-4o-mini"))

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

    # LM Studio (or any OpenAI-compatible local server) can be used by setting:
    #   OPENAI_API_URL=http://localhost:1234/v1
    #   OPENAI_API_KEY=dummy-key
    #   OPENAI_MODEL=<your-local-model>

    # Logging configuration
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    # Message limit configuration
    MAX_MESSAGES = int(os.getenv("MAX_MESSAGES", "500"))

    # Redis configuration for Active Memory (Tier 1) storage
    REDIS_ENABLED = os.getenv("REDIS_ENABLED", "false").lower() == "true"
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
    REDIS_DB = int(os.getenv("REDIS_DB", "0"))

    # T2 semantic memory uses the same Redis Stack service as T1/coordination.
    # Key prefixes separate tiers; logical Redis DB separation is kept only for compatibility.

    # Tavily API configuration for Web Search
    TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", None)
    TAVILY_API_URL = os.getenv("TAVILY_API_URL", "https://api.tavily.com")
    TAVILY_MAX_RESULTS = int(os.getenv("TAVILY_MAX_RESULTS", "5"))
    TAVILY_SEARCH_DEPTH = os.getenv("TAVILY_SEARCH_DEPTH", "basic")
    TAVILY_TIMEOUT = int(os.getenv("TAVILY_TIMEOUT", "30"))

    # CodeBox API configuration for Python code execution (Sandbox)
    CODEBOX_API_URL = os.getenv("CODEBOX_API_URL", "http://localhost:8069")
    CODEBOX_TIMEOUT = int(os.getenv("CODEBOX_TIMEOUT", "60"))  # seconds
    CODEBOX_MAX_OUTPUT_CHARS = int(os.getenv("CODEBOX_MAX_OUTPUT_CHARS", "2000"))  # Discord limit
    CODEBOX_SESSION_TTL = int(os.getenv("CODEBOX_SESSION_TTL", "1800"))  # 30 minutes

    # Bash Executor configuration (execute_host_bash tool)
    BASH_EXECUTOR_URL = os.getenv("BASH_EXECUTOR_URL", "http://host.docker.internal:8374")
    BASH_EXECUTOR_TIMEOUT = int(os.getenv("BASH_EXECUTOR_TIMEOUT", "30"))
    BASH_EXECUTOR_ALLOWED_ORIGINS = os.getenv("BASH_EXECUTOR_ALLOWED_ORIGINS", "march7-bot,http://localhost:8374,http://host.docker.internal:8374")

    # Evernight A2A URL (for March7 gateway to reach Evernight container)
    EVERNIGHT_A2A_URL = os.getenv("EVERNIGHT_A2A_URL", "http://evernight:8001")

    # Search Memory configuration
    SEARCH_TOP_K_SEMANTIC = int(os.getenv("SEARCH_TOP_K_SEMANTIC", "5"))
    SEARCH_TOP_K_TIME = int(os.getenv("SEARCH_TOP_K_TIME", "10"))
    SEARCH_TOP_K_TOPIC = int(os.getenv("SEARCH_TOP_K_TOPIC", "10"))
    SEARCH_MIN_RELEVANCE = float(os.getenv("SEARCH_MIN_RELEVANCE", "0.3"))

    # Embedding model configuration
    # Only OpenAI-compatible embeddings are supported (POST /embeddings).
    # Use EMBEDDING_PROVIDER=openai_compat (or openai) to make this explicit.
    # Backwards-compat: "qwen" is accepted as an alias for openai_compat.
    EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "openai_compat")
    EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "text-embedding-v3")
    EMBEDDING_API_URL = os.getenv("EMBEDDING_API_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1")
    # Backwards-compatible fallback: if you previously used QWEN_API_KEY for embeddings,
    # it will still be picked up when EMBEDDING_API_KEY is not set.
    EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", os.getenv("QWEN_API_KEY"))
    EMBEDDING_VECTOR_SIZE = int(os.getenv("EMBEDDING_VECTOR_SIZE", "1024"))
