import logging
from typing import Any, Dict, List

from src.services.working_memory.context_manager import WorkingMemoryEntry

logger = logging.getLogger(__name__)


class TokenManager:
    """
    Service for managing token counting and limiting for working memory entries.
    Handles token estimation and context window size management.
    """

    def __init__(self, max_tokens: int = 4096, model_name: str = "default"):
        self.max_tokens = max_tokens
        self.model_name = model_name
        # Token estimation factors (approximate)
        self.avg_token_per_word = 1.3
        self.avg_token_per_char = 0.25

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate the number of tokens in a text string.
        Uses a simple heuristic based on word count and character count.
        """
        if not text:
            return 0

        # Simple token estimation
        words = len(text.split())
        chars = len(text)

        # Weighted average of both methods
        word_based_tokens = int(words * self.avg_token_per_word)
        char_based_tokens = int(chars * self.avg_token_per_char)

        # Use the higher estimate to be conservative
        return max(word_based_tokens, char_based_tokens)

    def estimate_entry_tokens(self, entry: WorkingMemoryEntry) -> int:
        """
        Estimate tokens for a working memory entry.
        Includes role and content.
        """
        total_tokens = 0
        total_tokens += self.estimate_tokens(entry.role)
        total_tokens += self.estimate_tokens(entry.content)
        return total_tokens

    def get_context_within_token_limit(
        self, entries: List[WorkingMemoryEntry], max_tokens: int = None
    ) -> List[WorkingMemoryEntry]:
        """
        Get context entries that fit within the token limit.
        Returns entries from newest to oldest until token limit is reached.
        """
        if not entries:
            return []

        limit = max_tokens or self.max_tokens
        current_tokens = 0
        selected_entries = []

        # Process entries from newest to oldest (reverse order)
        for entry in reversed(entries):
            entry_tokens = self.estimate_entry_tokens(entry)
            if current_tokens + entry_tokens <= limit:
                selected_entries.append(entry)
                current_tokens += entry_tokens
            else:
                break

        # Return in chronological order (oldest to newest)
        return list(reversed(selected_entries))

    def get_token_usage(self, entries: List[WorkingMemoryEntry]) -> Dict[str, int]:
        """
        Get token usage statistics for a list of entries.
        """
        total_tokens = 0
        entry_tokens = []

        for entry in entries:
            tokens = self.estimate_entry_tokens(entry)
            entry_tokens.append(tokens)
            total_tokens += tokens

        return {
            "total_tokens": total_tokens,
            "entry_tokens": entry_tokens,
            "max_tokens": self.max_tokens,
            "remaining_tokens": max(0, self.max_tokens - total_tokens),
        }
