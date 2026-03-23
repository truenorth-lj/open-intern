"""Cost guard — daily budget enforcement and rate limiting for agents."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import sqlalchemy

from core.database import get_engine

logger = logging.getLogger(__name__)


# Approximate cost per 1M tokens (USD) by provider/model family.
# Used when exact pricing isn't available. Conservative estimates.
MODEL_COST_PER_1M: dict[str, dict[str, float]] = {
    "anthropic": {"input": 3.0, "output": 15.0},
    "claude": {"input": 3.0, "output": 15.0},
    "openai": {"input": 2.5, "output": 10.0},
    "minimax": {"input": 1.0, "output": 1.0},
    "ollama": {"input": 0.0, "output": 0.0},
}

DEFAULT_COST = {"input": 3.0, "output": 15.0}


class BudgetExceededError(Exception):
    """Raised when an agent's daily cost budget is exceeded."""

    def __init__(self, agent_id: str, spent: float, budget: float):
        self.agent_id = agent_id
        self.spent = spent
        self.budget = budget
        super().__init__(
            f"Agent '{agent_id}' daily budget exceeded: ${spent:.4f} spent of ${budget:.2f} limit"
        )


class RateLimitExceededError(Exception):
    """Raised when an agent exceeds its hourly action rate limit."""

    def __init__(self, agent_id: str, count: int, limit: int):
        self.agent_id = agent_id
        self.count = count
        self.limit = limit
        super().__init__(
            f"Agent '{agent_id}' hourly rate limit exceeded: "
            f"{count} actions in the last hour (limit: {limit})"
        )


class CostGuard:
    """Enforces daily spending caps and hourly rate limits per agent.

    Queries the token_usage table to compute approximate cost, and
    compares against the agent's configured daily_cost_budget_usd.
    """

    def __init__(
        self,
        database_url: str,
        agent_id: str,
        daily_budget_usd: float = 10.0,
        max_actions_per_hour: int = 60,
        provider: str = "anthropic",
    ):
        self._engine = get_engine(database_url)
        self.agent_id = agent_id
        self.daily_budget_usd = daily_budget_usd
        self.max_actions_per_hour = max_actions_per_hour
        self._cost_rates = MODEL_COST_PER_1M.get(provider, DEFAULT_COST)

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Estimate cost in USD for a given number of tokens."""
        input_cost = (input_tokens / 1_000_000) * self._cost_rates["input"]
        output_cost = (output_tokens / 1_000_000) * self._cost_rates["output"]
        return input_cost + output_cost

    def get_daily_spend(self) -> float:
        """Query today's total estimated spend from token_usage table."""
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        with self._engine.connect() as conn:
            row = conn.execute(
                sqlalchemy.text(
                    "SELECT COALESCE(SUM(input_tokens), 0) AS input_tokens, "
                    "COALESCE(SUM(output_tokens), 0) AS output_tokens "
                    "FROM token_usage "
                    "WHERE agent_id = :agent_id AND created_at >= :today_start"
                ),
                {"agent_id": self.agent_id, "today_start": today_start},
            ).first()

        if not row:
            return 0.0
        return self.estimate_cost(row.input_tokens, row.output_tokens)

    def get_hourly_action_count(self) -> int:
        """Count the number of actions in the last hour."""
        from datetime import timedelta

        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        with self._engine.connect() as conn:
            row = conn.execute(
                sqlalchemy.text(
                    "SELECT COUNT(*) AS cnt FROM token_usage "
                    "WHERE agent_id = :agent_id AND created_at >= :since"
                ),
                {"agent_id": self.agent_id, "since": one_hour_ago},
            ).first()
        return row.cnt if row else 0

    def check_budget(self) -> None:
        """Check if the agent is within its daily budget. Raises BudgetExceededError if not."""
        if self.daily_budget_usd <= 0:
            return  # No budget limit configured

        spent = self.get_daily_spend()
        if spent >= self.daily_budget_usd:
            logger.warning(
                f"Cost guard: agent '{self.agent_id}' exceeded daily budget "
                f"(${spent:.4f} / ${self.daily_budget_usd:.2f})"
            )
            raise BudgetExceededError(self.agent_id, spent, self.daily_budget_usd)

    def check_rate_limit(self) -> None:
        """Check if the agent is within its hourly rate limit."""
        if self.max_actions_per_hour <= 0:
            return  # No rate limit

        count = self.get_hourly_action_count()
        if count >= self.max_actions_per_hour:
            logger.warning(
                f"Cost guard: agent '{self.agent_id}' exceeded hourly rate limit "
                f"({count} / {self.max_actions_per_hour})"
            )
            raise RateLimitExceededError(self.agent_id, count, self.max_actions_per_hour)

    def check(self) -> None:
        """Run all guards. Raises on any violation."""
        self.check_budget()
        self.check_rate_limit()

    def get_status(self) -> dict:
        """Return current cost guard status for dashboard display."""
        spent = self.get_daily_spend()
        hourly_count = self.get_hourly_action_count()
        return {
            "agent_id": self.agent_id,
            "daily_budget_usd": self.daily_budget_usd,
            "daily_spent_usd": round(spent, 4),
            "budget_remaining_usd": round(max(0, self.daily_budget_usd - spent), 4),
            "budget_utilization_pct": round(
                (spent / self.daily_budget_usd * 100) if self.daily_budget_usd > 0 else 0, 1
            ),
            "hourly_action_count": hourly_count,
            "hourly_action_limit": self.max_actions_per_hour,
        }
