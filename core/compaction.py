"""Context compaction — summarize old conversation turns to free up context window."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Default threshold: compact when message count exceeds this
DEFAULT_MAX_MESSAGES = 40
# Keep the most recent N messages intact (don't summarize them)
DEFAULT_KEEP_RECENT = 10


def count_messages(result: dict[str, Any]) -> int:
    """Count the number of messages in an agent result/state."""
    messages = result.get("messages", [])
    return len(messages)


def needs_compaction(
    result: dict[str, Any],
    max_messages: int = DEFAULT_MAX_MESSAGES,
) -> bool:
    """Check if the conversation history needs compaction."""
    return count_messages(result) > max_messages


async def compact_context(
    llm: Any,
    messages: list,
    keep_recent: int = DEFAULT_KEEP_RECENT,
) -> tuple[list, str]:
    """Compact conversation history by summarizing older messages.

    Args:
        llm: The LLM instance (ChatModel) to use for summarization.
        messages: Full list of conversation messages.
        keep_recent: Number of recent messages to keep intact.

    Returns:
        Tuple of (new_messages, summary_text).
        new_messages starts with a system summary message followed by keep_recent messages.
    """
    import asyncio

    if len(messages) <= keep_recent:
        return messages, ""

    # Split into old messages (to summarize) and recent messages (to keep)
    old_messages = messages[:-keep_recent]
    recent_messages = messages[-keep_recent:]

    # Build a summary of the old messages
    summary_text = await asyncio.to_thread(_summarize_messages, llm, old_messages)

    # Create a synthetic system message with the summary
    from langchain_core.messages import SystemMessage

    summary_msg = SystemMessage(
        content=(
            f"[CONVERSATION SUMMARY — earlier messages compacted]\n\n"
            f"{summary_text}\n\n"
            f"[END SUMMARY — recent messages follow]"
        )
    )

    new_messages = [summary_msg] + recent_messages
    logger.info(
        f"Compacted {len(old_messages)} old messages into summary "
        f"({len(summary_text)} chars), keeping {len(recent_messages)} recent"
    )
    return new_messages, summary_text


def _summarize_messages(llm: Any, messages: list) -> str:
    """Synchronously summarize a list of messages using the LLM."""
    # Format messages into a readable transcript
    transcript_lines = []
    for msg in messages:
        role = getattr(msg, "type", "unknown")
        content = getattr(msg, "content", "")
        if isinstance(content, list):
            # Handle structured content blocks
            text_parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    text_parts.append(block)
            content = " ".join(text_parts)
        if content:
            transcript_lines.append(f"[{role}]: {content[:500]}")

    transcript = "\n".join(transcript_lines[-50:])  # Limit to last 50 for summary input

    prompt = (
        "Summarize this conversation concisely, preserving:\n"
        "1. Key decisions and conclusions\n"
        "2. Important facts and context mentioned\n"
        "3. Action items or commitments\n"
        "4. Any user preferences or corrections expressed\n\n"
        "Be concise but thorough. Use bullet points.\n\n"
        f"Conversation:\n{transcript}"
    )

    try:
        result = llm.invoke(prompt)
        content = result.content
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    return block["text"]
            return str(content)
        return str(content)
    except Exception as e:
        logger.error(f"Failed to summarize messages: {e}")
        # Fallback: simple truncation summary
        return (
            f"[Summary generation failed. {len(messages)} earlier messages "
            "were removed to free context.]"
        )
