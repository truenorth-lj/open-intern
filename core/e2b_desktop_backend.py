"""E2B Desktop sandbox backend — extends E2B with GUI, browser, and live streaming."""

from __future__ import annotations

import logging

from core.e2b_backend import E2BSandboxBackend

logger = logging.getLogger(__name__)


class E2BDesktopBackend(E2BSandboxBackend):
    """Backend that uses E2B Desktop sandbox with GUI, browser, and VNC streaming.

    Inherits all file/shell operations from E2BSandboxBackend, but uses
    the e2b-desktop Sandbox which includes a full Xfce desktop, Chrome,
    Firefox, and noVNC streaming.
    """

    def __init__(
        self,
        agent_id: str,
        *,
        timeout: int = 300,
        api_key: str | None = None,
        sandbox_id: str | None = None,
    ):
        # Desktop sandboxes don't use a custom template — e2b-desktop has its own
        super().__init__(
            agent_id,
            template="base",  # overridden by connect()
            timeout=timeout,
            api_key=api_key,
            sandbox_id=sandbox_id,
        )
        self._stream_url: str | None = None
        self._auth_key: str | None = None

    def connect(self) -> None:
        """Create or resume an E2B Desktop sandbox."""
        from e2b_desktop import Sandbox

        kwargs = {}
        if self._api_key:
            kwargs["api_key"] = self._api_key

        if self._existing_sandbox_id:
            try:
                self._sandbox = Sandbox.connect(self._existing_sandbox_id, **kwargs)
                logger.info(
                    f"Reconnected to E2B Desktop sandbox {self._existing_sandbox_id} "
                    f"for agent {self._agent_id}"
                )
                return
            except Exception:
                logger.warning(
                    f"Could not reconnect to desktop sandbox "
                    f"{self._existing_sandbox_id}, creating new one"
                )

        self._sandbox = Sandbox.create(
            timeout=self._default_timeout,
            metadata={"agent_id": self._agent_id},
            **kwargs,
        )
        logger.info(
            f"Created E2B Desktop sandbox {self._sandbox.sandbox_id} for agent {self._agent_id}"
        )

    # --- Streaming ---

    def start_stream(self, *, require_auth: bool = True) -> str:
        """Start VNC streaming and return the stream URL.

        Args:
            require_auth: Whether to require auth key in URL (default True).

        Returns:
            The noVNC stream URL that can be opened in a browser.
        """
        sbx = self._ensure_sandbox()
        sbx.stream.start(require_auth=require_auth)
        if require_auth:
            self._auth_key = sbx.stream.get_auth_key()
            self._stream_url = sbx.stream.get_url(auth_key=self._auth_key)
        else:
            self._stream_url = sbx.stream.get_url()
        logger.info(f"Desktop stream started for agent {self._agent_id}")
        return self._stream_url

    def stop_stream(self) -> None:
        """Stop the VNC stream."""
        if self._sandbox:
            try:
                self._sandbox.stream.stop()
                logger.info(f"Desktop stream stopped for agent {self._agent_id}")
            except Exception as e:
                logger.warning(f"Failed to stop stream: {e}")
        self._stream_url = None
        self._auth_key = None

    @property
    def stream_url(self) -> str | None:
        """Get the current stream URL, or None if not streaming."""
        return self._stream_url

    # --- Browser / GUI control ---

    def launch_browser(self, url: str | None = None) -> None:
        """Launch Chrome in the desktop sandbox, optionally navigating to a URL."""
        sbx = self._ensure_sandbox()
        sbx.launch("google-chrome")
        sbx.wait(3000)
        if url:
            sbx.press(["ctrl", "l"])
            sbx.wait(300)
            sbx.write(url)
            sbx.press("enter")
            sbx.wait(2000)

    def screenshot(self) -> bytes:
        """Take a screenshot of the desktop. Returns PNG bytes."""
        sbx = self._ensure_sandbox()
        return sbx.screenshot()

    def desktop_click(self, x: int, y: int) -> None:
        """Click at coordinates on the desktop."""
        sbx = self._ensure_sandbox()
        sbx.left_click(x, y)

    def desktop_type(self, text: str) -> None:
        """Type text on the desktop."""
        sbx = self._ensure_sandbox()
        sbx.write(text)

    def desktop_press(self, keys: str | list[str]) -> None:
        """Press a key or key combination."""
        sbx = self._ensure_sandbox()
        sbx.press(keys)

    def desktop_scroll(self, amount: int) -> None:
        """Scroll the desktop. Positive = up, negative = down."""
        sbx = self._ensure_sandbox()
        sbx.scroll(amount)

    # --- Lifecycle overrides ---

    def pause(self) -> str | None:
        """Stop stream before pausing."""
        self.stop_stream()
        return super().pause()

    def kill(self) -> None:
        """Stop stream before killing."""
        self.stop_stream()
        super().kill()
