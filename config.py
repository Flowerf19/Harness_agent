"""
Arize Phoenix Tool Kit Configuration
Cấu hình cho SDK tracing và LLM services.
"""
import os

# ============================================================
# Phoenix Configuration
# ============================================================
PHOENIX_COLLECTOR_ENDPOINT = os.getenv(
    "PHOENIX_COLLECTOR_ENDPOINT",
    "http://localhost:4317"
)

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