"""T2 timeline memory — public API."""
from twin.shared.memory.timeline.constants import (
    EMBEDDING_DIM,
    KNN_NEIGHBOURS_FOR_PRE_FLIGHT,
    MAX_CATALOGS_PER_MEMORY,
    TTL_BY_IMPORTANCE,
)
from twin.shared.memory.timeline.models import (
    CATALOG_TO_T3,
    CATALOGS,
    T2Memory,
    T3_PROMOTABLE,
    expires_at_for_importance,
    get_ttl_by_importance,
    new_uuid,
    utc_now,
)
from twin.shared.memory.timeline.store import TimelineStore
from twin.shared.memory.timeline.search import (
    TimelineSearch,
    format_preflight_for_prompt,
)

__all__ = [
    "T2Memory", "TimelineStore", "TimelineSearch",
    "format_preflight_for_prompt",
    "CATALOGS", "T3_PROMOTABLE", "CATALOG_TO_T3",
    "EMBEDDING_DIM", "TTL_BY_IMPORTANCE", "MAX_CATALOGS_PER_MEMORY",
    "KNN_NEIGHBOURS_FOR_PRE_FLIGHT", "utc_now", "new_uuid",
]
