"""Shared utilities for platform integrations."""

from __future__ import annotations


def chunk_message(content: str, max_size: int) -> list[str]:
    """Split a message into chunks that fit within a platform's size limit.

    Prefers splitting at newlines for readability. The newline at the split
    point is consumed (not included in either chunk) to avoid leading/trailing
    whitespace. Falls back to hard split if no newline is found.

    Content is fully preserved except for the single newline at each split point.
    """
    if len(content) <= max_size:
        return [content]

    chunks: list[str] = []
    remaining = content
    while remaining:
        if len(remaining) <= max_size:
            chunks.append(remaining)
            break
        # Try to split at last newline within limit
        split_at = remaining.rfind("\n", 0, max_size)
        if split_at <= 0:
            # No newline found — hard split at limit
            split_at = max_size
            chunks.append(remaining[:split_at])
            remaining = remaining[split_at:]
        else:
            # Split at newline: consume the newline itself
            chunks.append(remaining[:split_at])
            remaining = remaining[split_at + 1 :]  # skip the \n
    return chunks
