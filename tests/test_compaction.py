"""Tests for the context compaction module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.compaction import (
    DEFAULT_MAX_MESSAGES,
    compact_context,
    count_messages,
    needs_compaction,
)


class TestCountMessages:
    def test_empty(self):
        assert count_messages({}) == 0
        assert count_messages({"messages": []}) == 0

    def test_with_messages(self):
        msgs = [MagicMock() for _ in range(15)]
        assert count_messages({"messages": msgs}) == 15


class TestNeedsCompaction:
    def test_below_threshold(self):
        msgs = [MagicMock() for _ in range(DEFAULT_MAX_MESSAGES - 1)]
        assert not needs_compaction({"messages": msgs})

    def test_above_threshold(self):
        msgs = [MagicMock() for _ in range(DEFAULT_MAX_MESSAGES + 1)]
        assert needs_compaction({"messages": msgs})

    def test_custom_threshold(self):
        msgs = [MagicMock() for _ in range(11)]
        assert needs_compaction({"messages": msgs}, max_messages=10)
        assert not needs_compaction({"messages": msgs}, max_messages=20)


class TestCompactContext:
    @pytest.mark.anyio
    async def test_short_conversation_unchanged(self):
        msgs = [MagicMock() for _ in range(5)]
        llm = MagicMock()
        result, summary = await compact_context(llm, msgs, keep_recent=10)
        assert result == msgs  # Not enough to compact
        assert summary == ""

    @pytest.mark.anyio
    async def test_compaction_produces_summary(self):
        # Create mock messages
        msgs = []
        for i in range(30):
            msg = MagicMock()
            msg.type = "human" if i % 2 == 0 else "ai"
            msg.content = f"Message {i}"
            msgs.append(msg)

        # Mock LLM (async ainvoke)
        llm = MagicMock()
        mock_result = MagicMock()
        mock_result.content = "Summary of conversation"
        llm.ainvoke = AsyncMock(return_value=mock_result)

        result, summary = await compact_context(llm, msgs, keep_recent=10)

        # Should have 1 summary message + 10 recent messages
        assert len(result) == 11
        assert summary == "Summary of conversation"
        # First message should be the summary
        assert "CONVERSATION SUMMARY" in result[0].content
        # Last messages should be the original recent ones
        assert result[-1] == msgs[-1]

    @pytest.mark.anyio
    async def test_llm_failure_produces_fallback(self):
        msgs = []
        for i in range(30):
            msg = MagicMock()
            msg.type = "human"
            msg.content = f"Message {i}"
            msgs.append(msg)

        llm = MagicMock()
        llm.ainvoke = AsyncMock(side_effect=Exception("LLM error"))

        result, summary = await compact_context(llm, msgs, keep_recent=10)
        assert len(result) == 11
        assert "Summary generation failed" in summary
