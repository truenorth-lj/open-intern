"""Tests for integration utilities."""

from __future__ import annotations

from integrations.utils import chunk_message


class TestChunkMessage:
    def test_short_message_returns_single_chunk(self):
        assert chunk_message("hello", 100) == ["hello"]

    def test_empty_message(self):
        assert chunk_message("", 100) == [""]

    def test_exact_limit(self):
        msg = "x" * 100
        assert chunk_message(msg, 100) == [msg]

    def test_splits_long_message(self):
        msg = "a" * 250
        chunks = chunk_message(msg, 100)
        assert len(chunks) > 1
        joined = "".join(chunks)
        assert joined == msg

    def test_splits_at_newline(self):
        msg = "line1\nline2\nline3\nline4"
        chunks = chunk_message(msg, 12)
        # Should prefer splitting at newlines
        assert all(len(c) <= 12 for c in chunks)
        # Content should be preserved (minus stripped newlines at split points)
        assert "line1" in chunks[0]

    def test_hard_split_when_no_newline(self):
        msg = "a" * 300  # No newlines
        chunks = chunk_message(msg, 100)
        assert len(chunks) == 3
        assert all(len(c) <= 100 for c in chunks)

    def test_discord_limit(self):
        msg = "x" * 5000
        chunks = chunk_message(msg, 2000)
        assert all(len(c) <= 2000 for c in chunks)
        assert "".join(chunks) == msg

    def test_telegram_limit(self):
        msg = "x" * 10000
        chunks = chunk_message(msg, 4096)
        assert all(len(c) <= 4096 for c in chunks)
        assert "".join(chunks) == msg


class TestTelegramThreadBound:
    def test_thread_eviction_at_capacity(self):
        """Threads dict should evict oldest when at capacity."""
        from unittest.mock import MagicMock

        from integrations.telegram.bot import TelegramBot

        agent = MagicMock()
        agent.config = MagicMock()
        bot = TelegramBot(agent, token="test:token", agent_id="test")
        bot._MAX_THREADS = 5  # Small limit for testing

        # Fill to capacity
        for i in range(5):
            bot._get_thread_id(i)
        assert len(bot._threads) == 5

        # Adding one more should evict the oldest
        bot._get_thread_id(99)
        assert len(bot._threads) == 5
        assert 0 not in bot._threads  # First entry evicted
        assert 99 in bot._threads
