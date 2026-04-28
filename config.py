"""
Cấu hình cho SDK tracing và LLM services.
"""
import os

# ============================================================
# HuggingFace Configuration
# ============================================================
HF_TOKEN = os.getenv("HF_TOKEN", "")

# ============================================================
# Tool LLM Configuration (LM Studio / Ollama / OpenAI compatible)
# ============================================================
TOOL_LLM_ENDPOINT = os.getenv(
    "TOOL_LLM_ENDPOINT",
    "http://localhost:1234/v1"
)
TOOL_LLM_MODEL = os.getenv(
    "TOOL_LLM_MODEL",
    "local-model"
)
TOOL_LLM_API_KEY = os.getenv(
    "TOOL_LLM_API_KEY",
    "lm-studio-no-key-needed"
)

# ============================================================
# LLM Health Check Configuration
# ============================================================
LLM_HEALTH_CHECK_TIMEOUT = int(os.getenv("LLM_HEALTH_CHECK_TIMEOUT", "10"))
LLM_HEALTH_CHECK_RETRIES = int(os.getenv("LLM_HEALTH_CHECK_RETRIES", "3"))
LLM_HEALTH_CHECK_RETRY_DELAY = float(os.getenv("LLM_HEALTH_CHECK_RETRY_DELAY", "1.0"))

# ============================================================
# Ollama Configuration
# ============================================================
OLLAMA_ENDPOINT = os.getenv(
    "OLLAMA_ENDPOINT",
    "http://localhost:11434"
)

# ============================================================
# OpenAI Configuration
# ============================================================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

# ============================================================
# Search Memory Configuration
# ============================================================
SEARCH_TOP_K_SEMANTIC = int(os.getenv("SEARCH_TOP_K_SEMANTIC", "5"))
SEARCH_TOP_K_TIME = int(os.getenv("SEARCH_TOP_K_TIME", "10"))
SEARCH_TOP_K_TOPIC = int(os.getenv("SEARCH_TOP_K_TOPIC", "10"))
SEARCH_MIN_RELEVANCE = float(os.getenv("SEARCH_MIN_RELEVANCE", "0.3"))