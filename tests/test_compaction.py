"""Tests for the context compaction module."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.compaction import (
    DEFAULT_MAX_MESSAGES,
    SUMMARY_MARKER,
    compact_context,
    count_messages,
    is_summary_message,
    needs_compaction,
)


def _make_msg(role: str = "human", content: str = "hello") -> MagicMock:
    """Create a mock message with a valid string id."""
    msg = MagicMock()
    msg.type = role
    msg.content = content
    msg.id = str(uuid.uuid4())
    return msg


class TestCountMessages:
    def test_empty(self):
        assert count_messages({}) == 0
        assert count_messages({"messages": []}) == 0

    def test_with_messages(self):
        msgs = [_make_msg() for _ in range(15)]
        assert count_messages({"messages": msgs}) == 15


class TestNeedsCompaction:
    def test_below_threshold(self):
        msgs = [_make_msg() for _ in range(DEFAULT_MAX_MESSAGES - 1)]
        assert not needs_compaction({"messages": msgs})

    def test_above_threshold(self):
        msgs = [_make_msg() for _ in range(DEFAULT_MAX_MESSAGES + 1)]
        assert needs_compaction({"messages": msgs})

    def test_custom_threshold(self):
        msgs = [_make_msg() for _ in range(11)]
        assert needs_compaction({"messages": msgs}, max_messages=10)
        assert not needs_compaction({"messages": msgs}, max_messages=20)


class TestIsSummaryMessage:
    def test_summary_message(self):
        msg = _make_msg(content=f"{SUMMARY_MARKER}\n\nSome summary")
        assert is_summary_message(msg)

    def test_regular_message(self):
        msg = _make_msg(content="Hello, how are you?")
        assert not is_summary_message(msg)


class TestCompactContext:
    @pytest.mark.anyio
    async def test_short_conversation_unchanged(self):
        msgs = [_make_msg() for _ in range(5)]
        llm = MagicMock()
        removals, new_msgs, summary = await compact_context(llm, msgs, keep_recent=10)
        assert removals == []
        assert new_msgs == []
        assert summary == ""

    @pytest.mark.anyio
    async def test_compaction_produces_summary(self):
        msgs = []
        for i in range(30):
            msgs.append(_make_msg(
                role="human" if i % 2 == 0 else "ai",
                content=f"Message {i}",
            ))

        llm = MagicMock()
        mock_result = MagicMock()
        mock_result.content = "Summary of conversation"
        llm.ainvoke = AsyncMock(return_value=mock_result)

        removals, new_msgs, summary = await compact_context(llm, msgs, keep_recent=10)

        # Should produce removal instructions for the 20 old messages
        assert len(removals) == 20
        # Should produce 1 summary message
        assert len(new_msgs) == 1
        assert summary == "Summary of conversation"
        assert SUMMARY_MARKER in new_msgs[0].content

    @pytest.mark.anyio
    async def test_llm_failure_produces_fallback(self):
        msgs = [_make_msg(content=f"Message {i}") for i in range(30)]

        llm = MagicMock()
        llm.ainvoke = AsyncMock(side_effect=Exception("LLM error"))

        removals, new_msgs, summary = await compact_context(llm, msgs, keep_recent=10)
        assert len(removals) == 20
        assert len(new_msgs) == 1
        assert "Summary generation failed" in summary
