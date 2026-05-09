import logging
from typing import List

from langsmith import traceable

from ..models import MemoryEntry

logger = logging.getLogger(__name__)


class ContextBuilder:
    """Build context for LLM from T1 memory entries."""

    @traceable(
        name="T1_Build_Context",
        run_type="chain",
        tags=["tier_1", "management", "context"],
    )
    def build_context(self, entries: List[MemoryEntry], max_entries: int = 6) -> List[dict]:
        """
        Get the most recent entries for LLM context.

        Simplified: Since importance_score is always 0.0 (no evaluation pipeline),
        we just take the N most recent entries sorted by timestamp.

        Args:
            entries: List of memory entries
            max_entries: Maximum entries to include (default 6)

        Returns:
            List of {"role": "...", "content": "..."} dicts
        """
        if not entries:
            return []

        # Sort by timestamp (old -> new)
        sorted_entries = sorted(entries, key=lambda x: x.timestamp)

        # Take the N most recent entries
        recent_entries = sorted_entries[-max_entries:] if len(sorted_entries) > max_entries else sorted_entries

        # Format for LLM (omit metadata to save tokens)
        return [{"role": e.role, "content": e.content} for e in recent_entries]
