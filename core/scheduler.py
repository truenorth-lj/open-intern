"""Cron scheduler — persistent scheduled jobs that trigger agent actions."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import sqlalchemy
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from langchain_core.tools import tool
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from memory.store import ScheduledJobRecord

if TYPE_CHECKING:
    from core.manager import AgentManager

logger = logging.getLogger(__name__)


class CronScheduler:
    """Manages scheduled jobs backed by PostgreSQL and executed via APScheduler."""

    def __init__(self, database_url: str):
        sa_url = database_url
        if sa_url.startswith("postgresql+psycopg://"):
            sa_url = sa_url.replace("postgresql+psycopg://", "postgresql://", 1)
        self._engine = create_engine(sa_url, pool_size=5, max_overflow=10, pool_pre_ping=True)
        self._session_factory = sessionmaker(bind=self._engine)
        self._scheduler = AsyncIOScheduler()
        self._agent_manager: AgentManager | None = None

    def initialize(self, agent_manager: AgentManager) -> None:
        """Load jobs from DB, schedule them, and start the scheduler."""
        self._agent_manager = agent_manager
        self._load_jobs()
        self._scheduler.start()
        logger.info("CronScheduler started")

    def _load_jobs(self) -> None:
        """Load all enabled jobs from DB and schedule them."""
        with self._session_factory() as session:
            records = session.query(ScheduledJobRecord).filter_by(enabled=True).all()
            for rec in records:
                try:
                    self._schedule_job(rec)
                    logger.info(f"Scheduled job: {rec.id} ({rec.name})")
                except Exception as e:
                    logger.error(f"Failed to schedule job {rec.id}: {e}")

    def _build_trigger(self, record: ScheduledJobRecord):
        """Build an APScheduler trigger from a job record."""
        if record.schedule_type == "cron":
            return CronTrigger.from_crontab(record.schedule_expr, timezone=record.timezone)
        elif record.schedule_type == "interval":
            seconds = int(record.schedule_expr)
            return IntervalTrigger(seconds=seconds, timezone=record.timezone)
        elif record.schedule_type == "once":
            run_date = datetime.fromisoformat(record.schedule_expr)
            return DateTrigger(run_date=run_date, timezone=record.timezone)
        else:
            raise ValueError(f"Unknown schedule_type: {record.schedule_type}")

    def _schedule_job(self, record: ScheduledJobRecord) -> None:
        """Add a job to the APScheduler runtime."""
        trigger = self._build_trigger(record)
        self._scheduler.add_job(
            self._execute_job,
            trigger=trigger,
            id=record.id,
            args=[record.id],
            replace_existing=True,
            name=record.name,
        )

    async def _execute_job(self, job_id: str) -> None:
        """Execute a scheduled job: invoke agent.chat() with the stored prompt."""
        if not self._agent_manager:
            logger.error("No agent manager available for job execution")
            return

        # Load job from DB (fresh read for latest state)
        with self._session_factory() as session:
            record = session.query(ScheduledJobRecord).filter_by(id=job_id).first()
            if not record or not record.enabled:
                return
            agent_id = record.agent_id
            prompt = record.prompt
            channel_id = record.channel_id
            job_name = record.name
            isolated = record.isolated

        logger.info(f"Executing scheduled job: {job_name} (agent: {agent_id})")

        try:
            agent = self._agent_manager.get(agent_id)
            if not agent:
                raise RuntimeError(f"Agent '{agent_id}' not available")

            context: dict[str, Any] = {
                "platform": "scheduler",
                "channel_id": channel_id or "scheduled-task",
                "user_name": "scheduler",
                "is_dm": False,
            }
            # isolated: fresh thread each run; persistent: reuse same thread
            thread_id = f"cron:{job_id}:{uuid4()}" if isolated else f"cron:{job_id}"
            response = await agent.chat(prompt, context=context, thread_id=thread_id)

            # Update last run status
            self._update_job_status(job_id, "success")
            logger.info(
                f"Job {job_name} completed. Response: {response[:200]}..."
                if len(response) > 200
                else f"Job {job_name} completed. Response: {response}"
            )
        except Exception as e:
            self._update_job_status(job_id, "error", str(e))
            logger.error(f"Job {job_name} failed: {e}")

    def _update_job_status(self, job_id: str, status: str, error: str | None = None) -> None:
        """Update job's last_run_at, last_run_status, and next_run_at."""
        now = datetime.now(timezone.utc)
        # Compute next run from APScheduler
        next_run = None
        aps_job = self._scheduler.get_job(job_id)
        if aps_job and aps_job.next_run_time:
            next_run = aps_job.next_run_time

        with self._engine.connect() as conn:
            result = conn.execute(
                sqlalchemy.text(
                    "UPDATE scheduled_jobs SET "
                    "last_run_at = :last_run_at, "
                    "last_run_status = :status, "
                    "last_run_error = :error, "
                    "next_run_at = :next_run, "
                    "updated_at = :updated_at "
                    "WHERE id = :id"
                ),
                {
                    "last_run_at": now,
                    "status": status,
                    "error": error,
                    "next_run": next_run,
                    "updated_at": now,
                    "id": job_id,
                },
            )
            conn.commit()
            if result.rowcount == 0:
                logger.warning(f"Job {job_id} not found when updating status")

    async def add_job(
        self,
        agent_id: str,
        name: str,
        schedule_type: str,
        schedule_expr: str,
        prompt: str,
        tz: str = "UTC",
        channel_id: str = "",
        isolated: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        """Create a new scheduled job in DB and schedule it."""
        now = datetime.now(timezone.utc)
        job_id = str(uuid4())

        record = ScheduledJobRecord(
            id=job_id,
            agent_id=agent_id,
            name=name,
            schedule_type=schedule_type,
            schedule_expr=schedule_expr,
            timezone=tz,
            prompt=prompt,
            channel_id=channel_id,
            isolated=isolated,
            enabled=True,
            created_at=now,
            updated_at=now,
            metadata_json=json.dumps(metadata or {}),
        )

        # Validate "once" schedule is in the future
        if schedule_type == "once":
            run_date = datetime.fromisoformat(schedule_expr)
            if run_date.tzinfo is None:
                run_date = run_date.replace(tzinfo=timezone.utc)
            if run_date <= now:
                raise ValueError("'once' schedule must be in the future")

        # Schedule it first to validate the expression
        self._schedule_job(record)

        # Compute next_run_at from APScheduler
        aps_job = self._scheduler.get_job(job_id)
        next_run = aps_job.next_run_time if aps_job else None

        # Insert via raw SQL in a single transaction
        with self._engine.connect() as conn:
            conn.execute(
                sqlalchemy.text(
                    "INSERT INTO scheduled_jobs "
                    "(id, agent_id, name, schedule_type, schedule_expr, timezone, "
                    "prompt, channel_id, isolated, enabled, created_at, updated_at, "
                    "metadata_json, next_run_at) "
                    "VALUES (:id, :agent_id, :name, :schedule_type, :schedule_expr, "
                    ":timezone, :prompt, :channel_id, :isolated, :enabled, :created_at, "
                    ":updated_at, :metadata_json, :next_run_at)"
                ),
                {
                    "id": job_id,
                    "agent_id": agent_id,
                    "name": name,
                    "schedule_type": schedule_type,
                    "schedule_expr": schedule_expr,
                    "timezone": tz,
                    "prompt": prompt,
                    "channel_id": channel_id,
                    "isolated": isolated,
                    "enabled": True,
                    "created_at": now,
                    "updated_at": now,
                    "metadata_json": json.dumps(metadata or {}),
                    "next_run_at": next_run,
                },
            )
            conn.commit()

        logger.info(f"Created scheduled job: {job_id} ({name})")
        return {
            "id": job_id,
            "agent_id": agent_id,
            "name": name,
            "schedule_type": schedule_type,
            "schedule_expr": schedule_expr,
            "timezone": tz,
            "prompt": prompt,
            "channel_id": channel_id,
            "isolated": isolated,
            "enabled": True,
            "last_run_at": None,
            "last_run_status": None,
            "last_run_error": None,
            "next_run_at": next_run.isoformat() if next_run else None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "metadata": metadata or {},
        }

    async def remove_job(self, job_id: str) -> bool:
        """Remove a job: unschedule first, then delete from DB."""
        # Check existence
        with self._session_factory() as session:
            record = session.query(ScheduledJobRecord).filter_by(id=job_id).first()
            if not record:
                return False

        # Unschedule first (safe if not scheduled)
        try:
            self._scheduler.remove_job(job_id)
        except Exception:
            pass

        # Then delete from DB
        with self._session_factory() as session:
            record = session.query(ScheduledJobRecord).filter_by(id=job_id).first()
            if record:
                session.delete(record)
                session.commit()

        logger.info(f"Removed scheduled job: {job_id}")
        return True

    async def update_job(self, job_id: str, **kwargs) -> dict | None:
        """Update job fields and reschedule if schedule changed."""
        allowed = {
            "name",
            "schedule_type",
            "schedule_expr",
            "timezone",
            "prompt",
            "channel_id",
            "isolated",
            "enabled",
        }
        schedule_changed = False
        with self._session_factory() as session:
            record = session.query(ScheduledJobRecord).filter_by(id=job_id).first()
            if not record:
                return None

            for key, value in kwargs.items():
                if key not in allowed:
                    continue
                if key in ("schedule_type", "schedule_expr", "timezone"):
                    schedule_changed = True
                setattr(record, key, value)

            record.updated_at = datetime.now(timezone.utc)
            session.commit()
            result = self._job_to_dict(record)

        # Reschedule if needed
        if schedule_changed or "enabled" in kwargs:
            try:
                self._scheduler.remove_job(job_id)
            except Exception:
                pass
            if result["enabled"]:
                with self._session_factory() as session:
                    record = session.query(ScheduledJobRecord).filter_by(id=job_id).first()
                    if record:
                        self._schedule_job(record)

        return result

    async def pause_job(self, job_id: str) -> bool:
        """Disable a job."""
        result = await self.update_job(job_id, enabled=False)
        return result is not None

    async def resume_job(self, job_id: str) -> bool:
        """Re-enable a job."""
        result = await self.update_job(job_id, enabled=True)
        return result is not None

    async def trigger_job(self, job_id: str) -> bool:
        """Manually trigger a job immediately (one-shot)."""
        with self._session_factory() as session:
            record = session.query(ScheduledJobRecord).filter_by(id=job_id).first()
            if not record:
                return False

        await self._execute_job(job_id)
        return True

    def list_jobs(self, agent_id: str | None = None) -> list[dict]:
        """List all jobs, optionally filtered by agent_id."""
        with self._session_factory() as session:
            q = session.query(ScheduledJobRecord)
            if agent_id:
                q = q.filter_by(agent_id=agent_id)
            q = q.order_by(ScheduledJobRecord.created_at.desc())
            return [self._job_to_dict(r) for r in q.all()]

    def get_job(self, job_id: str) -> dict | None:
        """Get a single job by ID."""
        with self._session_factory() as session:
            record = session.query(ScheduledJobRecord).filter_by(id=job_id).first()
            if not record:
                return None
            return self._job_to_dict(record)

    def shutdown(self) -> None:
        """Gracefully stop the scheduler."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("CronScheduler stopped")

    @staticmethod
    def _job_to_dict(record: ScheduledJobRecord, next_run: datetime | None = None) -> dict:
        return {
            "id": record.id,
            "agent_id": record.agent_id,
            "name": record.name,
            "schedule_type": record.schedule_type,
            "schedule_expr": record.schedule_expr,
            "timezone": record.timezone,
            "prompt": record.prompt,
            "channel_id": record.channel_id,
            "isolated": record.isolated,
            "enabled": record.enabled,
            "last_run_at": record.last_run_at.isoformat() if record.last_run_at else None,
            "last_run_status": record.last_run_status,
            "last_run_error": record.last_run_error,
            "next_run_at": (
                next_run.isoformat()
                if next_run
                else (record.next_run_at.isoformat() if record.next_run_at else None)
            ),
            "created_at": record.created_at.isoformat() if record.created_at else "",
            "updated_at": record.updated_at.isoformat() if record.updated_at else "",
            "metadata": json.loads(record.metadata_json) if record.metadata_json else {},
        }


# --- Agent tools ---


def create_scheduler_tools(scheduler: CronScheduler, agent_id: str) -> list:
    """Create LangChain tools for an agent to manage its own scheduled jobs."""

    @tool
    async def create_scheduled_job(
        name: str,
        schedule_type: str,
        schedule_expr: str,
        prompt: str,
        timezone: str = "UTC",
        channel_id: str = "",
        isolated: bool = False,
    ) -> str:
        """Create a new scheduled job that will run automatically.

        Args:
            name: A short name for this job (e.g., "Daily standup summary").
            schedule_type: One of "cron", "interval", or "once".
                - "cron": Use a cron expression (e.g., "0 9 * * 1-5" for weekdays at 9am).
                - "interval": Run every N seconds (e.g., "3600" for hourly).
                - "once": Run once at a specific time (ISO 8601 timestamp).
            schedule_expr: The schedule expression matching the type above.
            prompt: The message/instruction to execute when the job triggers.
            timezone: IANA timezone (default "UTC"). E.g., "Asia/Shanghai", "US/Eastern".
            channel_id: Optional channel to deliver the response to.
            isolated: If True, each run uses a fresh conversation thread (no memory
                of previous runs). If False (default), all runs share the same thread
                so the agent can reference prior executions.
        """
        result = await scheduler.add_job(
            agent_id=agent_id,
            name=name,
            schedule_type=schedule_type,
            schedule_expr=schedule_expr,
            prompt=prompt,
            tz=timezone,
            channel_id=channel_id,
            isolated=isolated,
        )
        return (
            f"Created scheduled job '{result['name']}' (ID: {result['id']}). "
            f"Next run: {result.get('next_run_at', 'N/A')}"
        )

    @tool
    async def list_scheduled_jobs() -> str:
        """List all scheduled jobs for this agent."""
        jobs = scheduler.list_jobs(agent_id=agent_id)
        if not jobs:
            return "No scheduled jobs found."
        lines = []
        for j in jobs:
            status = "enabled" if j["enabled"] else "paused"
            last = j.get("last_run_status") or "never"
            lines.append(
                f"- {j['name']} (ID: {j['id'][:8]}…) "
                f"[{j['schedule_type']}: {j['schedule_expr']}] "
                f"status={status}, last_run={last}, "
                f"next={j.get('next_run_at', 'N/A')}"
            )
        return "\n".join(lines)

    @tool
    async def delete_scheduled_job(job_id: str) -> str:
        """Delete a scheduled job by its ID.

        Args:
            job_id: The job ID (UUID) to delete.
        """
        removed = await scheduler.remove_job(job_id)
        if removed:
            return f"Deleted scheduled job {job_id}."
        return f"Job {job_id} not found."

    @tool
    async def pause_scheduled_job(job_id: str) -> str:
        """Pause a scheduled job (stop it from running until resumed).

        Args:
            job_id: The job ID (UUID) to pause.
        """
        paused = await scheduler.pause_job(job_id)
        if paused:
            return f"Paused scheduled job {job_id}."
        return f"Job {job_id} not found."

    @tool
    async def resume_scheduled_job(job_id: str) -> str:
        """Resume a paused scheduled job.

        Args:
            job_id: The job ID (UUID) to resume.
        """
        resumed = await scheduler.resume_job(job_id)
        if resumed:
            return f"Resumed scheduled job {job_id}."
        return f"Job {job_id} not found."

    return [
        create_scheduled_job,
        list_scheduled_jobs,
        delete_scheduled_job,
        pause_scheduled_job,
        resume_scheduled_job,
    ]
