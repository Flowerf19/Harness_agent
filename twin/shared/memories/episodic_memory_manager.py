"""Backward-compatible import for the Redis-backed T2 memory facade."""

from twin.shared.memories.t2.memory import T2Memory


class EpisodicMemoryManager(T2Memory):
    """Compatibility alias.

    New code should use ``T2Memory``. The old name remains so existing tool and
    agent wiring does not need a broad rename.
    """

    def __init__(self, wiki_storage, embedding_service):
        super().__init__(store=wiki_storage, embedding_service=embedding_service)

    def _build_search_content(self, page) -> str:
        parts = [
            getattr(page, "canonical_topic", ""),
            getattr(page, "current_summary", ""),
        ]
        parts.extend(getattr(page, "key_points", []) or [])
        return "\n".join(part for part in parts if part)
