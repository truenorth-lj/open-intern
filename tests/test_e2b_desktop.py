"""Tests for E2B Desktop sandbox backend and sandbox mode selection."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Mock deepagents to avoid import chain issues in test environment.
# Must happen before any core.e2b_* imports.
# ---------------------------------------------------------------------------
_deepagents_mock = MagicMock()
_deepagents_mock.backends.protocol.SandboxBackendProtocol = type("SandboxBackendProtocol", (), {})
for _mod in [
    "deepagents",
    "deepagents.backends",
    "deepagents.backends.protocol",
    "deepagents.backends.local_shell",
    "deepagents.backends.composite",
    "deepagents.backends.store",
    "deepagents.graph",
]:
    sys.modules.setdefault(_mod, _deepagents_mock if _mod == "deepagents" else MagicMock())
sys.modules["deepagents.backends.protocol"] = _deepagents_mock.backends.protocol
for _name in [
    "EditResult",
    "ExecuteResponse",
    "FileDownloadResponse",
    "FileInfo",
    "FileUploadResponse",
    "GrepMatch",
    "WriteResult",
]:
    setattr(_deepagents_mock.backends.protocol, _name, type(_name, (), {}))

from core.e2b_desktop_backend import E2BDesktopBackend  # noqa: E402


@pytest.fixture
def backend():
    return E2BDesktopBackend(agent_id="test-agent", api_key="e2b_test")


class TestDesktopBackendInit:
    def test_initial_state(self, backend):
        assert backend._agent_id == "test-agent"
        assert backend._stream_url is None
        assert backend._auth_key is None
        assert backend.stream_url is None

    def test_id_before_connect(self, backend):
        assert "test-agent" in backend.id


class TestDesktopStreaming:
    def test_start_stream(self, backend):
        mock_sbx = MagicMock()
        mock_sbx.stream.get_auth_key.return_value = "auth-key-123"
        mock_sbx.stream.get_url.return_value = "https://stream.e2b.dev/vnc?key=auth-key-123"
        backend._sandbox = mock_sbx

        with patch.object(backend, "_ensure_sandbox", return_value=mock_sbx):
            url = backend.start_stream()

        mock_sbx.stream.start.assert_called_once_with(require_auth=True)
        assert url == "https://stream.e2b.dev/vnc?key=auth-key-123"
        assert backend.stream_url == url

    def test_start_stream_no_auth(self, backend):
        mock_sbx = MagicMock()
        mock_sbx.stream.get_url.return_value = "https://stream.e2b.dev/vnc"
        backend._sandbox = mock_sbx

        with patch.object(backend, "_ensure_sandbox", return_value=mock_sbx):
            url = backend.start_stream(require_auth=False)

        mock_sbx.stream.start.assert_called_once_with(require_auth=False)
        assert url == "https://stream.e2b.dev/vnc"
        assert backend._auth_key is None

    def test_stop_stream_clears_url(self, backend):
        backend._stream_url = "https://stream.e2b.dev/vnc"
        backend._auth_key = "key"
        backend._sandbox = MagicMock()

        backend.stop_stream()

        assert backend.stream_url is None
        assert backend._auth_key is None

    def test_stop_stream_no_sandbox(self, backend):
        backend.stop_stream()
        assert backend.stream_url is None


class TestDesktopGUIControl:
    def test_launch_browser_with_url(self, backend):
        mock_sbx = MagicMock()
        backend._sandbox = mock_sbx

        with patch.object(backend, "_ensure_sandbox", return_value=mock_sbx):
            backend.launch_browser("https://example.com")

        mock_sbx.launch.assert_called_once_with("google-chrome")
        mock_sbx.press.assert_any_call(["ctrl", "l"])
        mock_sbx.write.assert_called_once_with("https://example.com")
        mock_sbx.press.assert_any_call("enter")

    def test_launch_browser_no_url(self, backend):
        mock_sbx = MagicMock()
        backend._sandbox = mock_sbx

        with patch.object(backend, "_ensure_sandbox", return_value=mock_sbx):
            backend.launch_browser()

        mock_sbx.launch.assert_called_once_with("google-chrome")
        mock_sbx.write.assert_not_called()

    def test_screenshot(self, backend):
        mock_sbx = MagicMock()
        mock_sbx.screenshot.return_value = b"\x89PNG..."
        backend._sandbox = mock_sbx

        with patch.object(backend, "_ensure_sandbox", return_value=mock_sbx):
            result = backend.screenshot()
        assert result == b"\x89PNG..."

    def test_desktop_click(self, backend):
        mock_sbx = MagicMock()
        backend._sandbox = mock_sbx

        with patch.object(backend, "_ensure_sandbox", return_value=mock_sbx):
            backend.desktop_click(100, 200)
        mock_sbx.left_click.assert_called_once_with(100, 200)

    def test_desktop_type(self, backend):
        mock_sbx = MagicMock()
        backend._sandbox = mock_sbx

        with patch.object(backend, "_ensure_sandbox", return_value=mock_sbx):
            backend.desktop_type("hello world")
        mock_sbx.write.assert_called_once_with("hello world")

    def test_desktop_press(self, backend):
        mock_sbx = MagicMock()
        backend._sandbox = mock_sbx

        with patch.object(backend, "_ensure_sandbox", return_value=mock_sbx):
            backend.desktop_press(["ctrl", "c"])
        mock_sbx.press.assert_called_once_with(["ctrl", "c"])


class TestDesktopLifecycle:
    def test_pause_stops_stream_first(self, backend):
        backend._sandbox = MagicMock()
        backend._stream_url = "https://stream.e2b.dev/vnc"
        backend._sandbox.pause.return_value = "sbx-123"

        sandbox_id = backend.pause()

        backend._sandbox.stream.stop.assert_called_once()
        assert backend.stream_url is None
        assert sandbox_id == "sbx-123"

    def test_kill_stops_stream_first(self, backend):
        mock_sbx = MagicMock()
        backend._sandbox = mock_sbx
        backend._stream_url = "https://stream.e2b.dev/vnc"

        backend.kill()

        # stream.stop() should have been called before sandbox was killed
        mock_sbx.stream.stop.assert_called_once()
        assert backend.stream_url is None
        assert backend._sandbox is None


class TestSandboxModeSelection:
    """Test that agent._create_shell_backend() picks the right backend class."""

    @patch.dict("os.environ", {"E2B_API_KEY": "e2b_test"})
    @patch("core.e2b_desktop_backend.E2BDesktopBackend")
    def test_desktop_mode_creates_desktop_backend(self, mock_cls):
        from core.agent import OpenInternAgent

        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance

        agent = OpenInternAgent.__new__(OpenInternAgent)
        agent.agent_id = "test"
        agent.sandbox_mode = "desktop"
        agent.e2b_sandbox_id = ""
        agent._e2b_backend = None

        result = agent._create_shell_backend()

        mock_cls.assert_called_once_with(agent_id="test", api_key="e2b_test", sandbox_id=None)
        assert result is mock_instance
        assert agent._e2b_backend is mock_instance

    @patch.dict("os.environ", {"E2B_API_KEY": "e2b_test"})
    @patch("core.e2b_backend.E2BSandboxBackend")
    def test_base_mode_creates_base_backend(self, mock_cls):
        from core.agent import OpenInternAgent

        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance

        agent = OpenInternAgent.__new__(OpenInternAgent)
        agent.agent_id = "test"
        agent.sandbox_mode = "base"
        agent.e2b_sandbox_id = ""
        agent._e2b_backend = None

        result = agent._create_shell_backend()

        mock_cls.assert_called_once()
        assert result is mock_instance

    @patch.dict("os.environ", {"E2B_API_KEY": ""})
    def test_none_mode_creates_local_backend(self):
        from core.agent import OpenInternAgent

        agent = OpenInternAgent.__new__(OpenInternAgent)
        agent.agent_id = "test"
        agent.sandbox_mode = "none"
        agent.e2b_sandbox_id = ""
        agent._e2b_backend = None

        result = agent._create_shell_backend()

        assert agent._e2b_backend is None
        assert result is not None
