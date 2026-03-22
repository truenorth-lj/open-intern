"""Tests for E2B sandbox pause-on-shutdown behavior."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.manager import AgentManager


@pytest.fixture
def mock_manager():
    """Create a manager with mocked agents that have E2B backends."""
    mgr = MagicMock(spec=AgentManager)
    mgr._agents = {}
    mgr._session_factory = MagicMock()
    mgr.pause_all_sandboxes = AgentManager.pause_all_sandboxes.__get__(mgr, AgentManager)
    mgr._update_sandbox_id = MagicMock()
    return mgr


def _make_agent(has_e2b: bool, sandbox_id: str = "sbx-123"):
    """Create a mock agent with or without an E2B backend."""
    agent = MagicMock()
    if has_e2b:
        backend = MagicMock()
        backend.pause.return_value = sandbox_id
        agent._e2b_backend = backend
    else:
        agent._e2b_backend = None
    return agent


class TestPauseAllSandboxes:
    def test_pauses_e2b_agents(self, mock_manager):
        agent1 = _make_agent(has_e2b=True, sandbox_id="sbx-aaa")
        agent2 = _make_agent(has_e2b=True, sandbox_id="sbx-bbb")
        mock_manager._agents = {"a1": agent1, "a2": agent2}

        mock_manager.pause_all_sandboxes()

        agent1._e2b_backend.pause.assert_called_once()
        agent2._e2b_backend.pause.assert_called_once()
        assert mock_manager._update_sandbox_id.call_count == 2
        mock_manager._update_sandbox_id.assert_any_call("a1", "sbx-aaa")
        mock_manager._update_sandbox_id.assert_any_call("a2", "sbx-bbb")

    def test_skips_agents_without_e2b(self, mock_manager):
        agent_local = _make_agent(has_e2b=False)
        agent_e2b = _make_agent(has_e2b=True, sandbox_id="sbx-ccc")
        mock_manager._agents = {"local": agent_local, "cloud": agent_e2b}

        mock_manager.pause_all_sandboxes()

        agent_e2b._e2b_backend.pause.assert_called_once()
        mock_manager._update_sandbox_id.assert_called_once_with("cloud", "sbx-ccc")

    def test_handles_pause_failure_gracefully(self, mock_manager):
        agent_ok = _make_agent(has_e2b=True, sandbox_id="sbx-ok")
        agent_fail = _make_agent(has_e2b=True)
        agent_fail._e2b_backend.pause.side_effect = RuntimeError("E2B API error")
        mock_manager._agents = {"ok": agent_ok, "fail": agent_fail}

        # Should not raise
        mock_manager.pause_all_sandboxes()

        # The successful one still gets saved
        mock_manager._update_sandbox_id.assert_called_once_with("ok", "sbx-ok")

    def test_no_agents(self, mock_manager):
        mock_manager._agents = {}
        mock_manager.pause_all_sandboxes()
        mock_manager._update_sandbox_id.assert_not_called()

    def test_pause_returns_none_skips_update(self, mock_manager):
        agent = _make_agent(has_e2b=True)
        agent._e2b_backend.pause.return_value = None
        mock_manager._agents = {"a": agent}

        mock_manager.pause_all_sandboxes()

        mock_manager._update_sandbox_id.assert_not_called()
