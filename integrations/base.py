"""Base integration interface — all chat platform plugins implement this."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from core.agent import OpenInternAgent

logger = logging.getLogger(__name__)


class ChatEvent:
    """A normalized chat event from any platform."""

    def __init__(
        self,
        platform: str,
        event_type: str,  # "message", "mention", "reaction", "thread_reply"
        channel_id: str,
        user_id: str,
        user_name: str,
        content: str,
        is_dm: bool = False,
        thread_id: str | None = None,
        raw: Any = None,
    ):
        self.platform = platform
        self.event_type = event_type
        self.channel_id = channel_id
        self.user_id = user_id
        self.user_name = user_name
        self.content = content
        self.is_dm = is_dm
        self.thread_id = thread_id
        self.raw = raw

    def to_context(self) -> dict[str, Any]:
        """Convert to agent context dict."""
        return {
            "platform": self.platform,
            "channel_id": self.channel_id,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "is_dm": self.is_dm,
            "thread_id": self.thread_id,
        }


class Integration(ABC):
    """Abstract base for all chat platform integrations."""

    def __init__(self, agent: OpenInternAgent):
        self.agent = agent

    @abstractmethod
    async def start(self) -> None:
        """Start the bot / connection."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully stop the bot."""
        ...

    @abstractmethod
    async def send_message(
        self, channel_id: str, content: str, thread_id: str | None = None
    ) -> None:
        """Send a message to a channel."""
        ...

    async def handle_event(self, event: ChatEvent) -> str | None:
        """Handle an incoming chat event. Returns the agent's response."""
        # Skip messages from the bot itself
        if self._is_self(event):
            return None

        # Let the agent process it
        thread_id = event.thread_id or event.channel_id
        if not thread_id:
            logger.warning(f"No thread_id or channel_id for event from {event.platform}")
        response = await self.agent.chat(
            event.content, context=event.to_context(), thread_id=thread_id
        )

        # Send response back
        if response:
            await self.send_message(
                event.channel_id,
                response,
                thread_id=event.thread_id,
            )

        return response

    @abstractmethod
    def _is_self(self, event: ChatEvent) -> bool:
        """Check if the event was sent by this bot."""
        ...
