"""Context compaction — summarize old conversation turns to free up context window."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Default threshold: compact when message count exceeds this
DEFAULT_MAX_MESSAGES = 40
# Keep the most recent N messages intact (don't summarize them)
DEFAULT_KEEP_RECENT = 10

# Marker prefix used to identify compaction summary messages.
# Stored as HumanMessage (not SystemMessage) so agent_node doesn't strip it.
SUMMARY_MARKER = "[CONTEXT SUMMARY]"


def count_messages(result: dict[str, Any]) -> int:
    """Count the number of messages in an agent result/state."""
    messages = result.get("messages", [])
    return len(messages)


def is_summary_message(msg: Any) -> bool:
    """Check if a message is a compaction summary."""
    content = getattr(msg, "content", "")
    if isinstance(content, str):
        return content.startswith(SUMMARY_MARKER)
    return False


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
) -> tuple[list, list, str]:
    """Compact conversation history by summarizing older messages.

    Args:
        llm: The LLM instance (ChatModel) to use for summarization.
        messages: Full list of conversation messages.
        keep_recent: Number of recent messages to keep intact.

    Returns:
        Tuple of (removal_messages, new_messages, summary_text).
        removal_messages: RemoveMessage instances for old messages to delete.
        new_messages: [summary_msg] to add after removal.
    """
    from langchain_core.messages import HumanMessage, RemoveMessage

    if len(messages) <= keep_recent:
        return [], [], ""

    # Split into old messages (to summarize) and recent messages (to keep)
    old_messages = messages[:-keep_recent]
    recent_messages = messages[-keep_recent:]

    # Filter out any previous summary messages from old_messages before summarizing
    non_summary_old = [m for m in old_messages if not is_summary_message(m)]

    # Native async summarization
    summary_text = await _summarize_messages_async(llm, non_summary_old)

    # Create a HumanMessage with summary marker (not SystemMessage,
    # so agent_node won't strip it during system prompt injection).
    summary_msg = HumanMessage(
        content=(f"{SUMMARY_MARKER}\n\n{summary_text}\n\n[END SUMMARY — recent messages follow]")
    )

    # Build RemoveMessage list for all old messages (including previous summaries)
    removals = [RemoveMessage(id=m.id) for m in old_messages if getattr(m, "id", None)]

    logger.info(
        f"Compacted {len(old_messages)} old messages into summary "
        f"({len(summary_text)} chars), keeping {len(recent_messages)} recent"
    )
    return removals, [summary_msg], summary_text


def _build_transcript(messages: list) -> str:
    """Format messages into a readable transcript for summarization."""
    transcript_lines = []
    for msg in messages:
        role = getattr(msg, "type", "unknown")
        content = getattr(msg, "content", "")
        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    text_parts.append(block)
            content = " ".join(text_parts)
        if content:
            transcript_lines.append(f"[{role}]: {content[:500]}")
    return "\n".join(transcript_lines[-50:])


async def _summarize_messages_async(llm: Any, messages: list) -> str:
    """Summarize messages using the LLM's native async ainvoke."""
    transcript = _build_transcript(messages)

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
        result = await llm.ainvoke(prompt)
        content = result.content
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    return block["text"]
            return str(content)
        return str(content)
    except Exception as e:
        logger.error(f"Failed to summarize messages: {e}")
        return (
            f"[Summary generation failed. {len(messages)} earlier messages "
            "were removed to free context.]"
        )
