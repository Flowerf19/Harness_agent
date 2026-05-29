"""T2 timeline memory — public API."""
from twin.shared.memory.timeline.constants import (
    CLEANUP_DEBOUNCE_SECONDS,
    CLEANUP_SUPERSEDE_THRESHOLD,
    CLEANUP_TOPIC_MERGE_THRESHOLD,
    EMBEDDING_DIM,
    KNN_NEIGHBOURS_FOR_PRE_FLIGHT,
    MAX_CANDIDATES_PER_TRANSCRIPT,
    MAX_CATALOGS_PER_MEMORY,
    T3_PROMOTE_MIN_CONFIDENCE,
    T3_PROMOTE_MIN_IMPORTANCE,
    TOPIC_CASCADE_LIMIT,
    TOPIC_MATCH_THRESHOLD_AUTO,
    TOPIC_MATCH_THRESHOLD_LLM,
    TOPIC_TTL_MULTIPLIER,
    TTL_BY_IMPORTANCE,
)
from twin.shared.memory.timeline.models import (
    CATALOG_TO_T3,
    CATALOGS,
    T2Memory,
    T2Topic,
    T3_PROMOTABLE,
    expires_at_for_importance,
    get_ttl_by_importance,
    new_uuid,
    topic_expires_at_for_importance,
    topic_ttl_for_importance,
    utc_now,
)
from twin.shared.memory.timeline.consolidator import (
    ConsolidationResult,
    Consolidator,
)
from twin.shared.memory.timeline.cleanup import Cleanup, CleanupReport
from twin.shared.memory.timeline.cleanup_scheduler import CleanupScheduler
from twin.shared.memory.timeline.extractor import (
    CandidateMemory,
    ExtractResult,
    Extractor,
)
from twin.shared.memory.timeline.store import TimelineStore
from twin.shared.memory.timeline.search import (
    TimelineSearch,
    format_preflight_for_prompt,
)
from twin.shared.memory.timeline.topic_resolver import TopicResolver

__all__ = [
    "T2Topic", "T2Memory", "TimelineStore", "TimelineSearch",
    "format_preflight_for_prompt", "TopicResolver",
    "Extractor", "Consolidator", "CandidateMemory", "ExtractResult",
    "ConsolidationResult",
    "Cleanup", "CleanupReport", "CleanupScheduler",
    "CATALOGS", "T3_PROMOTABLE", "CATALOG_TO_T3",
    "EMBEDDING_DIM", "TTL_BY_IMPORTANCE", "TOPIC_TTL_MULTIPLIER",
    "TOPIC_MATCH_THRESHOLD_AUTO", "TOPIC_MATCH_THRESHOLD_LLM",
    "TOPIC_CASCADE_LIMIT", "MAX_CANDIDATES_PER_TRANSCRIPT",
    "MAX_CATALOGS_PER_MEMORY", "KNN_NEIGHBOURS_FOR_PRE_FLIGHT",
    "T3_PROMOTE_MIN_IMPORTANCE", "T3_PROMOTE_MIN_CONFIDENCE",
    "CLEANUP_DEBOUNCE_SECONDS", "CLEANUP_SUPERSEDE_THRESHOLD",
    "CLEANUP_TOPIC_MERGE_THRESHOLD",
    "expires_at_for_importance", "topic_expires_at_for_importance",
    "get_ttl_by_importance", "topic_ttl_for_importance",
    "utc_now", "new_uuid",
]
