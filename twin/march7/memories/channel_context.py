from typing import List

from twin.march7.memories.activate_memory.models import MemoryEntry


def build_channel_context(
    entries: List[MemoryEntry],
    max_entries: int = 12,
    max_tokens: int = 1500,
) -> str:
    """Format channel entries as a readable transcript."""
    if not entries:
        return ""

    sorted_entries = sorted(entries, key=lambda e: e.timestamp)
    selected: list[MemoryEntry] = []
    total = 0

    for entry in reversed(sorted_entries):
        if len(selected) >= max_entries:
            break
        if selected and total + entry.tokens > max_tokens:
            break
        selected.append(entry)
        total += entry.tokens

    selected.reverse()
    lines = []
    for entry in selected:
        name = entry.author_name or entry.user_id
        lines.append(f"{name}: {entry.content}")
    return "\n".join(lines)
