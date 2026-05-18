import logging
from typing import List

from langsmith import traceable

from twin.shared.config.settings import Config

from ..models import MemoryEntry

logger = logging.getLogger(__name__)


class ContextBuilder:
    """Build context for LLM from T1 memory entries."""

    @traceable(
        name="T1_Build_Context",
        run_type="chain",
        tags=["tier_1", "management", "context"],
    )
    def build_context(
        self,
        entries: List[MemoryEntry],
        max_entries: int | None = None,
        max_tokens: int | None = None,
    ) -> List[dict]:
        """
        Get the most recent entries for LLM context within a token budget.

        Args:
            entries: List of memory entries
            max_entries: Maximum entries to include (default from T1_CONTEXT_MAX_MESSAGES)
            max_tokens: Maximum stored T1 tokens to include (default from T1_CONTEXT_MAX_TOKENS)

        Returns:
            List of {"role": "...", "content": "..."} dicts
        """
        if not entries:
            return []

        max_entries = max_entries if max_entries is not None else Config.T1_CONTEXT_MAX_MESSAGES
        max_tokens = max_tokens if max_tokens is not None else Config.T1_CONTEXT_MAX_TOKENS

        # Sort by timestamp (old -> new)
        sorted_entries = sorted(entries, key=lambda x: x.timestamp)

        selected: List[MemoryEntry] = []
        total_tokens = 0

        # Walk newest -> oldest so recent context has priority, then restore
        # chronological order before sending to the LLM.
        for entry in reversed(sorted_entries):
            if len(selected) >= max_entries:
                break
            if selected and total_tokens + entry.tokens > max_tokens:
                break
            selected.append(entry)
            total_tokens += entry.tokens

        selected.reverse()

        # Format for LLM (omit metadata to save tokens)
        return [{"role": e.role, "content": e.content} for e in selected]
