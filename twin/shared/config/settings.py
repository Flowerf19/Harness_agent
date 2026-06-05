# Shared runtime configuration loaded from environment.
#
# Keep only values that genuinely vary per deployment. Defaults that rarely
# need tuning live as plain constants below the Config class.
import os


# === Constants (rarely change; don't expose to .env) ===

# Discord message pacing — keeps the bot from looking instant/spammy.
PART_BREAK_DELAY = float(os.getenv("PART_BREAK_DELAY", "0.6"))

# Tavily search defaults.
TAVILY_SEARCH_DEPTH = "basic"
TAVILY_MAX_RESULTS_DEFAULT = 5
TAVILY_TIMEOUT_DEFAULT = 30

# Codebox runtime.
CODEBOX_TIMEOUT_DEFAULT = 60
CODEBOX_MAX_OUTPUT_CHARS_DEFAULT = 2000
CODEBOX_SESSION_TTL_DEFAULT = 1800  # 30 min

# Bash executor.
BASH_EXECUTOR_TIMEOUT_DEFAULT = 30

# Search / T2 retrieval — only SEMANTIC is currently consumed by the
# orchestrator; the time/topic knobs were never wired.
SEARCH_TOP_K_SEMANTIC_DEFAULT = 5
SEARCH_MIN_RELEVANCE_DEFAULT = 0.3


class Config:
    # === Discord / Gateway ===
    DISCORD_BOT_TOKEN = os.getenv("DISCORD_MARCH7_TOKEN")
    DISCORD_BOT_CLIENT_ID = os.getenv("DISCORD_MARCH7_CLIENT_ID")
    SYNC_COMMANDS = os.getenv("SYNC_COMMANDS", "0")

    # === LLM provider ===
    # Supported: "gemini" or "openai" (OpenAI-compatible — also covers
    # OpenRouter, LM Studio, Qwen compatible-mode, etc. via OPENAI_API_URL).
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")

    # Generation parameters (tuned per deployment).
    LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "4000"))
    LLM_TOP_P = float(os.getenv("LLM_TOP_P", "0.9"))
    LLM_TOP_K = int(os.getenv("LLM_TOP_K", "40"))
    LLM_FREQUENCY_PENALTY = float(os.getenv("LLM_FREQUENCY_PENALTY", "0.4"))
    LLM_PRESENCE_PENALTY = float(os.getenv("LLM_PRESENCE_PENALTY", "0.1"))
    LLM_REQUEST_TIMEOUT = int(os.getenv("LLM_REQUEST_TIMEOUT", "120"))
    LLM_CONNECT_TIMEOUT = int(os.getenv("LLM_CONNECT_TIMEOUT", "10"))

    # OpenAI-compatible endpoint.
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "dummy-key")
    OPENAI_API_URL = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # Gemini.
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GEMINI_API_URL = os.getenv("GEMINI_API_URL", "https://generativelanguage.googleapis.com/v1beta/models")

    # === Discord message pacing ===
    PART_BREAK_DELAY = PART_BREAK_DELAY

    # === Logging ===
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    # === Redis / T1 ===
    REDIS_ENABLED = os.getenv("REDIS_ENABLED", "false").lower() == "true"
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
    REDIS_DB = int(os.getenv("REDIS_DB", "0"))
    TIMELINE_REDIS_DB = int(os.getenv("TIMELINE_REDIS_DB", "0"))
    # T1 storage phases:
    #   redis_stack  — Redis Stack JSON/Search (default)
    #   legacy       — Redis HASH fallback
    T1_STORAGE_PHASE = os.getenv("T1_STORAGE_PHASE", "redis_stack").lower()
    T1_CONTEXT_MAX_TOKENS = int(os.getenv("T1_CONTEXT_MAX_TOKENS", "1800"))
    T1_CONTEXT_MAX_MESSAGES = int(os.getenv("T1_CONTEXT_MAX_MESSAGES", "32"))

    # === Tavily (web search tool) ===
    TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", None)
    TAVILY_API_URL = os.getenv("TAVILY_API_URL", "https://api.tavily.com")
    TAVILY_MAX_RESULTS = int(os.getenv("TAVILY_MAX_RESULTS", str(TAVILY_MAX_RESULTS_DEFAULT)))
    TAVILY_SEARCH_DEPTH = TAVILY_SEARCH_DEPTH
    TAVILY_TIMEOUT = int(os.getenv("TAVILY_TIMEOUT", str(TAVILY_TIMEOUT_DEFAULT)))

    # === Codebox (sandboxed Python) ===
    CODEBOX_API_URL = os.getenv("CODEBOX_API_URL", "http://localhost:8069")
    CODEBOX_TIMEOUT = CODEBOX_TIMEOUT_DEFAULT
    CODEBOX_MAX_OUTPUT_CHARS = CODEBOX_MAX_OUTPUT_CHARS_DEFAULT
    CODEBOX_SESSION_TTL = CODEBOX_SESSION_TTL_DEFAULT

    # === Bash Executor (privileged host command) ===
    BASH_EXECUTOR_URL = os.getenv("BASH_EXECUTOR_URL", "http://host.docker.internal:8374")
    BASH_EXECUTOR_TIMEOUT = int(os.getenv("BASH_EXECUTOR_TIMEOUT", str(BASH_EXECUTOR_TIMEOUT_DEFAULT)))
    BASH_EXECUTOR_ALLOWED_ORIGINS = os.getenv(
        "BASH_EXECUTOR_ALLOWED_ORIGINS",
        "march7-bot,http://localhost:8374,http://host.docker.internal:8374",
    )

    # === Evernight A2A endpoint (March7 calls Evernight) ===
    EVERNIGHT_A2A_URL = os.getenv("EVERNIGHT_A2A_URL", "http://evernight:8001")

    # === Search Memory ===
    SEARCH_TOP_K_SEMANTIC = SEARCH_TOP_K_SEMANTIC_DEFAULT
    SEARCH_MIN_RELEVANCE = SEARCH_MIN_RELEVANCE_DEFAULT

    # === Embedding model ===
    # Supported providers (see twin/shared/llm/embedding/embedding_factory.py):
    #   - openai_compat (aliases: openai, qwen) -> OpenAIEmbeddingService
    #     Works with OpenAI, Qwen/DashScope, Voyage, LM Studio, OpenRouter, ...
    #   - gemini (alias: google) -> GeminiEmbeddingService
    EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "openai_compat")
    EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "text-embedding-v3")
    EMBEDDING_API_URL = os.getenv("EMBEDDING_API_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1")
    EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY")
    EMBEDDING_VECTOR_SIZE = int(os.getenv("EMBEDDING_VECTOR_SIZE", "768"))
