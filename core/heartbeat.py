"""Heartbeat — proactive background execution for agents.

The heartbeat system periodically runs the agent with a configurable checklist
(stored in the agent's workspace as HEARTBEAT.md). The agent processes the checklist
and only notifies if action is needed.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

if TYPE_CHECKING:
    from core.agent import OpenInternAgent

logger = logging.getLogger(__name__)

DEFAULT_HEARTBEAT_PROMPT = """\
You are running a periodic heartbeat check. Review your HEARTBEAT checklist below and \
take any actions needed. If nothing requires attention, respond with exactly "HEARTBEAT_OK".

## Checklist
- Check if there are any pending tasks or action items you committed to
- Review any scheduled deadlines approaching in the next 24 hours
- Check if any monitored channels have important unread activity
- Note any recurring reports that need to be generated

Only notify the user if you find something that requires their attention. \
Be concise in your report.
"""

MAX_CONSECUTIVE_FAILURES = 5


class HeartbeatRunner:
    """Manages periodic heartbeat execution for agents."""

    def __init__(self, scheduler: AsyncIOScheduler | None = None):
        self._scheduler = scheduler or AsyncIOScheduler()
        self._own_scheduler = scheduler is None
        self._agents: dict[str, OpenInternAgent] = {}
        self._failure_counts: dict[str, int] = {}
        self._last_run: dict[str, datetime] = {}
        self._heartbeat_prompts: dict[str, str] = {}

    def start(self) -> None:
        """Start the heartbeat scheduler if we own it."""
        if self._own_scheduler and not self._scheduler.running:
            self._scheduler.start()
            logger.info("Heartbeat scheduler started")

    def stop(self) -> None:
        """Stop the heartbeat scheduler if we own it."""
        if self._own_scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Heartbeat scheduler stopped")

    def register_agent(
        self,
        agent: OpenInternAgent,
        interval_minutes: int = 30,
        prompt: str = "",
        quiet_hours: str = "",
    ) -> None:
        """Register an agent for periodic heartbeat execution.

        Args:
            agent: The agent to run heartbeats for.
            interval_minutes: Minutes between heartbeat runs.
            prompt: Custom heartbeat prompt (uses default if empty).
            quiet_hours: Time range to skip heartbeats, e.g. "22:00-08:00".
        """
        agent_id = agent.agent_id
        self._agents[agent_id] = agent
        self._failure_counts[agent_id] = 0
        self._heartbeat_prompts[agent_id] = prompt or DEFAULT_HEARTBEAT_PROMPT

        job_id = f"heartbeat:{agent_id}"

        # Remove existing job if any
        try:
            self._scheduler.remove_job(job_id)
        except Exception:
            pass

        self._scheduler.add_job(
            self._run_heartbeat,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id=job_id,
            args=[agent_id, quiet_hours],
            replace_existing=True,
            name=f"Heartbeat for {agent_id}",
        )
        logger.info(
            f"Registered heartbeat for agent '{agent_id}' "
            f"(every {interval_minutes}min, quiet_hours={quiet_hours or 'none'})"
        )

    def unregister_agent(self, agent_id: str) -> None:
        """Stop heartbeats for an agent."""
        job_id = f"heartbeat:{agent_id}"
        try:
            self._scheduler.remove_job(job_id)
        except Exception:
            pass
        self._agents.pop(agent_id, None)
        self._failure_counts.pop(agent_id, None)
        self._heartbeat_prompts.pop(agent_id, None)
        logger.info(f"Unregistered heartbeat for agent '{agent_id}'")

    async def _run_heartbeat(self, agent_id: str, quiet_hours: str = "") -> None:
        """Execute a single heartbeat cycle for an agent."""
        if quiet_hours and _in_quiet_hours(quiet_hours):
            logger.debug(f"Heartbeat skipped for '{agent_id}' (quiet hours)")
            return

        agent = self._agents.get(agent_id)
        if not agent or not agent.is_initialized:
            logger.warning(f"Heartbeat: agent '{agent_id}' not available")
            return

        # Check cost guard if available
        if hasattr(agent, "cost_guard") and agent.cost_guard:
            try:
                agent.cost_guard.check()
            except Exception as e:
                logger.info(f"Heartbeat skipped for '{agent_id}': {e}")
                return

        prompt = self._heartbeat_prompts.get(agent_id, DEFAULT_HEARTBEAT_PROMPT)
        thread_id = f"heartbeat:{agent_id}"

        try:
            response, _usage = await agent.chat(
                prompt,
                context={
                    "platform": "heartbeat",
                    "channel_id": "heartbeat",
                    "user_name": "system",
                    "is_dm": False,
                },
                thread_id=thread_id,
            )

            self._failure_counts[agent_id] = 0
            self._last_run[agent_id] = datetime.now(timezone.utc)

            # Only log if there's something noteworthy
            if response.strip().upper() != "HEARTBEAT_OK":
                logger.info(f"Heartbeat [{agent_id}] found action needed: {response[:200]}")
                # TODO: deliver notification to configured channel
            else:
                logger.debug(f"Heartbeat [{agent_id}]: OK")

        except Exception as e:
            self._failure_counts[agent_id] = self._failure_counts.get(agent_id, 0) + 1
            failures = self._failure_counts[agent_id]
            logger.error(f"Heartbeat [{agent_id}] failed ({failures}x): {e}")

            if failures >= MAX_CONSECUTIVE_FAILURES:
                logger.warning(
                    f"Heartbeat [{agent_id}] disabled after {failures} consecutive failures"
                )
                self.unregister_agent(agent_id)

    async def trigger_heartbeat(self, agent_id: str) -> dict[str, Any]:
        """Manually trigger a heartbeat for an agent. Returns the result."""
        agent = self._agents.get(agent_id)
        if not agent:
            return {"error": f"Agent '{agent_id}' not registered for heartbeat"}

        prompt = self._heartbeat_prompts.get(agent_id, DEFAULT_HEARTBEAT_PROMPT)
        thread_id = f"heartbeat:{agent_id}"

        try:
            response, usage = await agent.chat(
                prompt,
                context={
                    "platform": "heartbeat",
                    "channel_id": "heartbeat",
                    "user_name": "system",
                    "is_dm": False,
                },
                thread_id=thread_id,
            )
            return {
                "agent_id": agent_id,
                "response": response,
                "token_usage": dict(usage),
                "status": "ok" if response.strip().upper() == "HEARTBEAT_OK" else "action_needed",
            }
        except Exception as e:
            return {"agent_id": agent_id, "error": str(e), "status": "error"}

    def get_status(self) -> list[dict[str, Any]]:
        """Get heartbeat status for all registered agents."""
        statuses = []
        for agent_id in self._agents:
            job_id = f"heartbeat:{agent_id}"
            aps_job = self._scheduler.get_job(job_id)
            next_run = aps_job.next_run_time if aps_job else None
            statuses.append(
                {
                    "agent_id": agent_id,
                    "last_run": self._last_run[agent_id].isoformat()
                    if agent_id in self._last_run
                    else None,
                    "next_run": next_run.isoformat() if next_run else None,
                    "consecutive_failures": self._failure_counts.get(agent_id, 0),
                }
            )
        return statuses


def _in_quiet_hours(quiet_hours: str) -> bool:
    """Check if current time is within quiet hours (e.g., '22:00-08:00')."""
    try:
        parts = quiet_hours.split("-")
        if len(parts) != 2:
            return False
        start_h, start_m = map(int, parts[0].strip().split(":"))
        end_h, end_m = map(int, parts[1].strip().split(":"))
        now = datetime.now(timezone.utc)
        current_minutes = now.hour * 60 + now.minute
        start_minutes = start_h * 60 + start_m
        end_minutes = end_h * 60 + end_m

        if start_minutes <= end_minutes:
            # Same day range (e.g., 08:00-17:00)
            return start_minutes <= current_minutes < end_minutes
        else:
            # Overnight range (e.g., 22:00-08:00)
            return current_minutes >= start_minutes or current_minutes < end_minutes
    except (ValueError, IndexError):
        return False
