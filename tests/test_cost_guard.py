"""Tests for the cost guard module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.cost_guard import (
    BudgetExceededError,
    CostGuard,
    RateLimitExceededError,
)


@pytest.fixture
def mock_engine():
    """Mock the database engine."""
    with patch("core.cost_guard.get_engine") as mock:
        engine = MagicMock()
        mock.return_value = engine
        yield engine


class TestCostEstimation:
    def test_estimate_cost_anthropic(self, mock_engine):
        guard = CostGuard(
            database_url="postgresql://test",
            agent_id="test",
            provider="anthropic",
        )
        # 1M input tokens at $3/1M + 1M output tokens at $15/1M = $18
        cost = guard.estimate_cost(1_000_000, 1_000_000)
        assert cost == pytest.approx(18.0)

    def test_estimate_cost_ollama_free(self, mock_engine):
        guard = CostGuard(
            database_url="postgresql://test",
            agent_id="test",
            provider="ollama",
        )
        cost = guard.estimate_cost(1_000_000, 1_000_000)
        assert cost == 0.0

    def test_estimate_cost_unknown_provider(self, mock_engine):
        guard = CostGuard(
            database_url="postgresql://test",
            agent_id="test",
            provider="unknown_provider",
        )
        # Should use default rates
        cost = guard.estimate_cost(1_000_000, 0)
        assert cost > 0


class TestBudgetCheck:
    def test_within_budget(self, mock_engine):
        guard = CostGuard(
            database_url="postgresql://test",
            agent_id="test",
            daily_budget_usd=10.0,
            provider="anthropic",
        )
        # Mock daily spend query to return low usage
        conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        row = MagicMock()
        row.input_tokens = 1000
        row.output_tokens = 500
        conn.execute.return_value.first.return_value = row

        guard.check_budget()  # Should not raise

    def test_over_budget_raises(self, mock_engine):
        guard = CostGuard(
            database_url="postgresql://test",
            agent_id="test",
            daily_budget_usd=0.01,
            provider="anthropic",
        )
        conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        row = MagicMock()
        row.input_tokens = 1_000_000  # $3 at anthropic rates
        row.output_tokens = 1_000_000  # $15 at anthropic rates
        conn.execute.return_value.first.return_value = row

        with pytest.raises(BudgetExceededError) as exc_info:
            guard.check_budget()
        assert exc_info.value.agent_id == "test"
        assert exc_info.value.spent > 0.01

    def test_zero_budget_skips_check(self, mock_engine):
        guard = CostGuard(
            database_url="postgresql://test",
            agent_id="test",
            daily_budget_usd=0.0,
        )
        guard.check_budget()  # Should not raise, no budget limit


class TestRateLimitCheck:
    def test_within_rate_limit(self, mock_engine):
        guard = CostGuard(
            database_url="postgresql://test",
            agent_id="test",
            max_actions_per_hour=60,
        )
        conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        row = MagicMock()
        row.cnt = 5
        conn.execute.return_value.first.return_value = row

        guard.check_rate_limit()  # Should not raise

    def test_over_rate_limit_raises(self, mock_engine):
        guard = CostGuard(
            database_url="postgresql://test",
            agent_id="test",
            max_actions_per_hour=10,
        )
        conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        row = MagicMock()
        row.cnt = 15
        conn.execute.return_value.first.return_value = row

        with pytest.raises(RateLimitExceededError):
            guard.check_rate_limit()

    def test_zero_rate_limit_skips(self, mock_engine):
        guard = CostGuard(
            database_url="postgresql://test",
            agent_id="test",
            max_actions_per_hour=0,
        )
        guard.check_rate_limit()  # Should not raise


class TestGetStatus:
    def test_returns_status_dict(self, mock_engine):
        guard = CostGuard(
            database_url="postgresql://test",
            agent_id="test-agent",
            daily_budget_usd=10.0,
            max_actions_per_hour=60,
        )
        conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        # Return different mocks for the two separate queries
        spend_row = MagicMock(input_tokens=100_000, output_tokens=50_000)
        action_row = MagicMock(cnt=10)
        conn.execute.return_value.first.side_effect = [spend_row, action_row]

        status = guard.get_status()
        assert status["agent_id"] == "test-agent"
        assert status["daily_budget_usd"] == 10.0
        assert status["daily_spent_usd"] >= 0
        assert status["hourly_action_count"] == 10
        assert status["hourly_action_limit"] == 60
