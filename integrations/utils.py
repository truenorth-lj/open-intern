"""Shared utilities for platform integrations."""

from __future__ import annotations


def chunk_message(content: str, max_size: int) -> list[str]:
    """Split a message into chunks that fit within a platform's size limit.

    Splits at the last newline before the limit to preserve formatting.
    Falls back to hard split if no newline is found.
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
            # No newline found — hard split with some margin
            split_at = max_size
        chunk = remaining[:split_at]
        chunks.append(chunk)
        remaining = remaining[split_at:].lstrip("\n")
    return chunks
