"""Tests for the CronScheduler service."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.scheduler import CronScheduler, create_scheduler_tools
from memory.store import ScheduledJobRecord


@pytest.fixture
def scheduler():
    """Create a CronScheduler with mocked DB."""
    s = CronScheduler.__new__(CronScheduler)
    s._engine = MagicMock()
    # Create a session mock that works as context manager
    session = MagicMock()
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    s._mock_session = session  # expose for test assertions
    s._session_factory = MagicMock(return_value=session)
    s._scheduler = MagicMock()
    s._agent_manager = None
    return s


class TestCronSchedulerBuildTrigger:
    """Test trigger construction from job records."""

    def _make_record(self, schedule_type: str, schedule_expr: str, tz: str = "UTC"):
        rec = MagicMock(spec=ScheduledJobRecord)
        rec.schedule_type = schedule_type
        rec.schedule_expr = schedule_expr
        rec.timezone = tz
        return rec

    def test_cron_trigger(self, scheduler):
        rec = self._make_record("cron", "0 9 * * 1-5")
        trigger = scheduler._build_trigger(rec)
        assert trigger is not None

    def test_interval_trigger(self, scheduler):
        rec = self._make_record("interval", "3600")
        trigger = scheduler._build_trigger(rec)
        assert trigger is not None

    def test_once_trigger(self, scheduler):
        rec = self._make_record("once", "2026-03-25T10:00:00+00:00")
        trigger = scheduler._build_trigger(rec)
        assert trigger is not None

    def test_invalid_type_raises(self, scheduler):
        rec = self._make_record("invalid", "foo")
        with pytest.raises(ValueError, match="Unknown schedule_type"):
            scheduler._build_trigger(rec)


class TestCronSchedulerJobToDict:
    """Test job record serialization."""

    def test_serializes_all_fields(self):
        now = datetime.now(timezone.utc)
        rec = MagicMock(spec=ScheduledJobRecord)
        rec.id = "test-id"
        rec.agent_id = "agent-1"
        rec.name = "Test Job"
        rec.schedule_type = "cron"
        rec.schedule_expr = "0 9 * * *"
        rec.timezone = "UTC"
        rec.prompt = "Hello"
        rec.channel_id = ""
        rec.enabled = True
        rec.last_run_at = now
        rec.last_run_status = "success"
        rec.last_run_error = None
        rec.next_run_at = now
        rec.created_at = now
        rec.updated_at = now
        rec.metadata_json = '{"key": "value"}'

        result = CronScheduler._job_to_dict(rec)

        assert result["id"] == "test-id"
        assert result["agent_id"] == "agent-1"
        assert result["name"] == "Test Job"
        assert result["schedule_type"] == "cron"
        assert result["enabled"] is True
        assert result["last_run_status"] == "success"
        assert result["metadata"] == {"key": "value"}

    def test_handles_none_datetimes(self):
        rec = MagicMock(spec=ScheduledJobRecord)
        rec.id = "test-id"
        rec.agent_id = "agent-1"
        rec.name = "Test"
        rec.schedule_type = "interval"
        rec.schedule_expr = "60"
        rec.timezone = "UTC"
        rec.prompt = "Hi"
        rec.channel_id = ""
        rec.enabled = True
        rec.last_run_at = None
        rec.last_run_status = None
        rec.last_run_error = None
        rec.next_run_at = None
        rec.created_at = None
        rec.updated_at = None
        rec.metadata_json = "{}"

        result = CronScheduler._job_to_dict(rec)
        assert result["last_run_at"] is None
        assert result["next_run_at"] is None


class TestSchedulerTools:
    """Test that scheduler tools are properly created."""

    def test_creates_six_tools(self):
        scheduler = MagicMock(spec=CronScheduler)
        tools = create_scheduler_tools(scheduler, "test-agent")
        assert len(tools) == 6
        names = {t.name for t in tools}
        assert names == {
            "create_scheduled_job",
            "list_scheduled_jobs",
            "update_scheduled_job",
            "delete_scheduled_job",
            "pause_scheduled_job",
            "resume_scheduled_job",
        }

    def test_update_tool_filters_empty_values(self):
        sched = MagicMock(spec=CronScheduler)
        sched.update_job.return_value = {"id": "abc-123", "name": "test"}
        tools = create_scheduler_tools(sched, "test-agent")
        update_tool = next(t for t in tools if t.name == "update_scheduled_job")
        result = update_tool.func(job_id="abc-123", name="new-name")
        sched.update_job.assert_called_once_with("abc-123", name="new-name")
        assert "Updated" in result

    def test_update_tool_no_fields_returns_error(self):
        sched = MagicMock(spec=CronScheduler)
        tools = create_scheduler_tools(sched, "test-agent")
        update_tool = next(t for t in tools if t.name == "update_scheduled_job")
        result = update_tool.func(job_id="abc-123")
        assert "No fields to update" in result
        sched.update_job.assert_not_called()

    def test_update_tool_invalid_schedule_type(self):
        sched = MagicMock(spec=CronScheduler)
        tools = create_scheduler_tools(sched, "test-agent")
        update_tool = next(t for t in tools if t.name == "update_scheduled_job")
        result = update_tool.func(job_id="abc-123", schedule_type="invalid")
        assert "Invalid schedule_type" in result
        sched.update_job.assert_not_called()

    def test_update_tool_invalid_delivery_platform(self):
        sched = MagicMock(spec=CronScheduler)
        tools = create_scheduler_tools(sched, "test-agent")
        update_tool = next(t for t in tools if t.name == "update_scheduled_job")
        result = update_tool.func(job_id="abc-123", delivery_platform="whatsapp")
        assert "Invalid delivery_platform" in result
        sched.update_job.assert_not_called()


@pytest.mark.anyio
class TestCronSchedulerAddJob:
    """Test job creation."""

    async def test_add_job_creates_record(self, scheduler):
        scheduler._scheduler.get_job.return_value = None

        # Mock the connection for raw SQL insert and next_run_at update
        conn = MagicMock()
        scheduler._engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
        scheduler._engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        result = scheduler.add_job(
            agent_id="agent-1",
            name="Test Job",
            schedule_type="interval",
            schedule_expr="60",
            prompt="Do something",
        )

        assert result["name"] == "Test Job"
        assert result["agent_id"] == "agent-1"
        assert result["schedule_type"] == "interval"
        assert result["enabled"] is True
        # Verify SQL was executed via engine.connect()
        conn.execute.assert_called()
        conn.commit.assert_called()


@pytest.mark.anyio
class TestCronSchedulerRemoveJob:
    """Test job removal."""

    async def test_remove_existing_job(self, scheduler):
        session = scheduler._mock_session
        record = MagicMock(spec=ScheduledJobRecord)
        session.query.return_value.filter_by.return_value.first.return_value = record

        result = scheduler.remove_job("job-id")
        assert result is True
        session.delete.assert_called_once_with(record)

    async def test_remove_nonexistent_job(self, scheduler):
        session = scheduler._mock_session
        session.query.return_value.filter_by.return_value.first.return_value = None

        result = scheduler.remove_job("nonexistent")
        assert result is False


@pytest.mark.anyio
class TestCronSchedulerExecuteJob:
    """Test job execution."""

    async def test_execute_calls_agent_chat(self, scheduler):
        # Setup mock agent
        agent = AsyncMock()
        empty_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        agent.chat.return_value = ("Done!", empty_usage)
        manager = MagicMock()
        manager.get.return_value = agent
        scheduler._agent_manager = manager

        # Setup mock DB record
        session = scheduler._mock_session
        record = MagicMock(spec=ScheduledJobRecord)
        record.id = "job-1"
        record.agent_id = "agent-1"
        record.prompt = "Do something"
        record.channel_id = ""
        record.name = "Test"
        record.enabled = True
        record.isolated = False
        record.delivery_platform = ""
        record.delivery_chat_id = ""
        session.query.return_value.filter_by.return_value.first.return_value = record

        # Mock _update_job_status
        scheduler._update_job_status = MagicMock()

        await scheduler._execute_job("job-1")

        agent.chat.assert_called_once()
        call_args = agent.chat.call_args
        assert call_args[0][0] == "Do something"
        scheduler._update_job_status.assert_called_once_with("job-1", "success")

    async def test_execute_retries_init_when_not_initialized(self, scheduler):
        """Agent that failed async init gets re-initialized before chat."""
        agent = AsyncMock()
        agent.is_initialized = False
        empty_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        agent.chat.return_value = ("Done!", empty_usage)

        # After initialize_async, mark as initialized
        async def _fix_init():
            agent.is_initialized = True

        agent.initialize_async.side_effect = _fix_init

        manager = MagicMock()
        manager.get.return_value = agent
        scheduler._agent_manager = manager

        session = scheduler._mock_session
        record = MagicMock(spec=ScheduledJobRecord)
        record.id = "job-1"
        record.agent_id = "agent-1"
        record.prompt = "Do something"
        record.channel_id = ""
        record.name = "Test"
        record.enabled = True
        record.isolated = False
        record.delivery_platform = ""
        record.delivery_chat_id = ""
        session.query.return_value.filter_by.return_value.first.return_value = record

        scheduler._update_job_status = MagicMock()

        await scheduler._execute_job("job-1")

        agent.initialize_async.assert_called_once()
        agent.chat.assert_called_once()
        scheduler._update_job_status.assert_called_once_with("job-1", "success")

    async def test_execute_handles_missing_agent(self, scheduler):
        manager = MagicMock()
        manager.get.return_value = None
        scheduler._agent_manager = manager

        session = scheduler._mock_session
        record = MagicMock(spec=ScheduledJobRecord)
        record.id = "job-1"
        record.agent_id = "missing-agent"
        record.prompt = "Do something"
        record.channel_id = ""
        record.name = "Test"
        record.enabled = True
        session.query.return_value.filter_by.return_value.first.return_value = record

        scheduler._update_job_status = MagicMock()

        await scheduler._execute_job("job-1")

        scheduler._update_job_status.assert_called_once()
        assert scheduler._update_job_status.call_args[0][1] == "error"
