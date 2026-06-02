"""Constants for T2 timeline memory."""
from __future__ import annotations

EMBEDDING_DIM = 768
TTL_BY_IMPORTANCE = {5: 90, 4: 60, 3: 30, 2: 14, 1: 7}
TOPIC_TTL_MULTIPLIER = 2
TOPIC_MATCH_THRESHOLD_AUTO = 0.92
TOPIC_MATCH_THRESHOLD_LLM = 0.75
TOPIC_CASCADE_LIMIT = 50
MAX_CANDIDATES_PER_TRANSCRIPT = 5
MAX_CATALOGS_PER_MEMORY = 2
# Output budget for the extractor's structured JSON call. Larger than the chat
# default because reasoning models spend tokens thinking before emitting JSON;
# too small a cap truncates the answer (or leaves only reasoning, no JSON).
EXTRACT_MAX_TOKENS = 4000
KNN_NEIGHBOURS_FOR_PRE_FLIGHT = 5
T3_PROMOTE_MIN_IMPORTANCE = 4
T3_PROMOTE_MIN_CONFIDENCE = 0.8
CLEANUP_DEBOUNCE_SECONDS = 30
CLEANUP_SUPERSEDE_THRESHOLD = 0.88
CLEANUP_TOPIC_MERGE_THRESHOLD = 0.90
