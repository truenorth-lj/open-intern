"""Tests for the heartbeat module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.heartbeat import HeartbeatRunner, _in_quiet_hours


class TestQuietHours:
    def test_same_day_range_inside(self):
        from datetime import datetime, timezone

        with patch("core.heartbeat.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert _in_quiet_hours("08:00-17:00")

    def test_same_day_range_outside(self):
        from datetime import datetime, timezone

        with patch("core.heartbeat.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 1, 20, 0, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert not _in_quiet_hours("08:00-17:00")

    def test_overnight_range_inside_late(self):
        from datetime import datetime, timezone

        with patch("core.heartbeat.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 1, 23, 0, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert _in_quiet_hours("22:00-08:00")

    def test_overnight_range_inside_early(self):
        from datetime import datetime, timezone

        with patch("core.heartbeat.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 1, 5, 0, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert _in_quiet_hours("22:00-08:00")

    def test_overnight_range_outside(self):
        from datetime import datetime, timezone

        with patch("core.heartbeat.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 1, 14, 0, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert not _in_quiet_hours("22:00-08:00")

    def test_invalid_format(self):
        assert not _in_quiet_hours("invalid")
        assert not _in_quiet_hours("")


class TestHeartbeatRunner:
    def test_register_and_unregister(self):
        runner = HeartbeatRunner()
        agent = MagicMock()
        agent.agent_id = "test-agent"
        agent.is_initialized = True

        runner.register_agent(agent, interval_minutes=15)
        assert "test-agent" in runner._agents

        runner.unregister_agent("test-agent")
        assert "test-agent" not in runner._agents

    @pytest.mark.anyio
    async def test_heartbeat_ok_response(self):
        runner = HeartbeatRunner()
        agent = MagicMock()
        agent.agent_id = "test-agent"
        agent.is_initialized = True
        usage = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
        agent.chat = AsyncMock(return_value=("HEARTBEAT_OK", usage))

        runner._agents["test-agent"] = agent
        runner._failure_counts["test-agent"] = 0

        await runner._run_heartbeat("test-agent")
        assert runner._failure_counts["test-agent"] == 0
        assert "test-agent" in runner._last_run

    @pytest.mark.anyio
    async def test_heartbeat_failure_increments_counter(self):
        runner = HeartbeatRunner()
        agent = MagicMock()
        agent.agent_id = "test-agent"
        agent.is_initialized = True
        agent.chat = AsyncMock(side_effect=Exception("LLM error"))

        runner._agents["test-agent"] = agent
        runner._failure_counts["test-agent"] = 0

        await runner._run_heartbeat("test-agent")
        assert runner._failure_counts["test-agent"] == 1

    @pytest.mark.anyio
    async def test_trigger_heartbeat(self):
        runner = HeartbeatRunner()
        agent = MagicMock()
        agent.agent_id = "test-agent"
        agent.is_initialized = True
        usage = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
        agent.chat = AsyncMock(return_value=("HEARTBEAT_OK", usage))

        runner._agents["test-agent"] = agent
        result = await runner.trigger_heartbeat("test-agent")
        assert result["status"] == "ok"
        assert result["response"] == "HEARTBEAT_OK"

    @pytest.mark.anyio
    async def test_trigger_unknown_agent(self):
        runner = HeartbeatRunner()
        result = await runner.trigger_heartbeat("unknown")
        assert "error" in result

    def test_get_status_empty(self):
        runner = HeartbeatRunner()
        assert runner.get_status() == []
