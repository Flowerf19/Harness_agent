# Shared runtime configuration loaded from environment.
#
# Keep only values that genuinely vary per deployment. Defaults that rarely
# need tuning live as plain constants below the Config class.
import os


# === Constants (rarely change; don't expose to .env) ===

# Discord message pacing — keeps the bot from looking instant/spammy.
PART_BREAK_DELAY = float(os.getenv("PART_BREAK_DELAY", "0.6"))

# Tavily MCP defaults.
TAVILY_TIMEOUT_DEFAULT = 30

# Codebox runtime.
CODEBOX_TIMEOUT_DEFAULT = 60
CODEBOX_MAX_OUTPUT_CHARS_DEFAULT = 2000
CODEBOX_SESSION_TTL_DEFAULT = 1800  # 30 min

# System Gateway.
SYSTEM_GATEWAY_TIMEOUT_DEFAULT = 30

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

    # Reasoning effort for OpenAI-compat endpoint.
    # Ollama openai.go maps this to native `think` param:
    #   "none"      -> think=false
    #   "low"|"medium"|"high"|"max" -> think="<level>"
    # Empty / unset = don't send the field, let provider/model decide.
    _LLM_REASONING_EFFORT_RAW = os.getenv("LLM_REASONING_EFFORT", "").strip().lower()
    _LLM_REASONING_EFFORT_VALID = {"", "none", "low", "medium", "high", "max"}
    if _LLM_REASONING_EFFORT_RAW not in _LLM_REASONING_EFFORT_VALID:
        raise ValueError(
            f"LLM_REASONING_EFFORT must be one of "
            f"{{'', 'none', 'low', 'medium', 'high', 'max'}}, "
            f"got: {_LLM_REASONING_EFFORT_RAW!r}"
        )
    LLM_REASONING_EFFORT = _LLM_REASONING_EFFORT_RAW or None

    # Consolidation is a JSON-extraction (Summarizer) task, not open reasoning.
    # Running it at the global reasoning_effort ("high") makes minimax "think"
    # for minutes on a large T1 prompt and blow past LLM_REQUEST_TIMEOUT, so it
    # gets its own lower effort + tighter token cap. Empty = don't send field.
    _LLM_CONSOLIDATION_EFFORT_RAW = os.getenv("LLM_CONSOLIDATION_REASONING_EFFORT", "low").strip().lower()
    if _LLM_CONSOLIDATION_EFFORT_RAW not in _LLM_REASONING_EFFORT_VALID:
        raise ValueError(
            f"LLM_CONSOLIDATION_REASONING_EFFORT must be one of "
            f"{{'', 'none', 'low', 'medium', 'high', 'max'}}, "
            f"got: {_LLM_CONSOLIDATION_EFFORT_RAW!r}"
        )
    LLM_CONSOLIDATION_REASONING_EFFORT = _LLM_CONSOLIDATION_EFFORT_RAW or None
    LLM_CONSOLIDATION_MAX_TOKENS = int(os.getenv("LLM_CONSOLIDATION_MAX_TOKENS", "4000"))

    # OpenAI tool_choice enforcement for Decide stage. Allowed: "" (off, don't send) /
    # "auto" / "required" / "none". Empty = current behavior (let LLM decide). Set
    # "required" to force a tool call when user intent clearly needs a tool — but note
    # Ollama OpenAI-compat proxy may silently ignore this field; test runtime before
    # relying on it.
    _LLM_TOOL_CHOICE_RAW = os.getenv("LLM_TOOL_CHOICE", "").strip().lower()
    LLM_TOOL_CHOICE = _LLM_TOOL_CHOICE_RAW or None

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
    TAVILY_TIMEOUT = int(os.getenv("TAVILY_TIMEOUT", str(TAVILY_TIMEOUT_DEFAULT)))
    TAVILY_MCP_URL = os.getenv("TAVILY_MCP_URL", "https://mcp.tavily.com/mcp")

    # === Codebox (sandboxed Python) ===
    CODEBOX_API_URL = os.getenv("CODEBOX_API_URL", "http://localhost:8069")
    CODEBOX_TIMEOUT = CODEBOX_TIMEOUT_DEFAULT
    CODEBOX_MAX_OUTPUT_CHARS = CODEBOX_MAX_OUTPUT_CHARS_DEFAULT
    CODEBOX_SESSION_TTL = CODEBOX_SESSION_TTL_DEFAULT

    # === System Gateway (native host boundary) ===
    SYSTEM_GATEWAY_URL = os.getenv("SYSTEM_GATEWAY_URL", "http://host.docker.internal:8380")
    SYSTEM_GATEWAY_TIMEOUT = int(
        os.getenv("SYSTEM_GATEWAY_TIMEOUT", str(SYSTEM_GATEWAY_TIMEOUT_DEFAULT))
    )
    SYSTEM_GATEWAY_SHARED_SECRET = os.getenv("SYSTEM_GATEWAY_SHARED_SECRET") or None

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
    EMBEDDING_VECTOR_SIZE = int(os.getenv("EMBEDDING_VECTOR_SIZE", "1024"))
    EMBEDDING_TRACE_LOG_ENABLED = (
        os.getenv("EMBEDDING_TRACE_LOG_ENABLED", "false").lower() == "true"
    )
    EMBEDDING_TRACE_LOG_PATH = os.getenv(
        "EMBEDDING_TRACE_LOG_PATH", "logs/embedding_trace.jsonl"
    )
    # Retrieval prefixes. Qwen3-Embedding is instruction-aware and ASYMMETRIC:
    # the QUERY side wants an instruct wrapper ("Instruct: ...\nQuery: <text>")
    # while the PASSAGE side wants raw text (empty prefix) — so changing only
    # the query prefix needs NO reindex. (e5-style models instead use
    # "query: "/"passage: ".) Provider-agnostic so the embedding model can be
    # switched via .env without touching call sites. Env values are stored on
    # one line with a literal backslash-n; both dotenv and docker env_file may
    # deliver it as two raw chars, so unescape it into a real newline here.
    EMBEDDING_QUERY_PREFIX = os.getenv(
        "EMBEDDING_QUERY_PREFIX",
        "Instruct: Given a user message, retrieve relevant memory summaries "
        "about the user and past conversation\nQuery: ",
    ).replace("\\n", "\n")
    EMBEDDING_PASSAGE_PREFIX = os.getenv("EMBEDDING_PASSAGE_PREFIX", "").replace("\\n", "\n")
    # T2 semantic-recall relevance gate: drop KNN hits whose cosine similarity
    # is below this before injecting into the prompt. 0.0 = off (legacy). A weak
    # embedding model (e.g. e5-small on Vietnamese) collapses all cosines into a
    # narrow high band, so this only bites once a discriminating model is used.
    T2_MIN_COSINE = float(os.getenv("T2_MIN_COSINE", "0.0"))
    # Archive raw T1 entries to a cold per-day Redis list on trim instead of
    # hard-deleting (W3): t1:archive:{scope}:{scope_id}:{day}. Best-effort —
    # an archive failure never blocks the trim.
    T1_ARCHIVE_ENABLED = os.getenv("T1_ARCHIVE_ENABLED", "true").lower() == "true"
    T1_ARCHIVE_TTL_DAYS = int(os.getenv("T1_ARCHIVE_TTL_DAYS", "90"))
