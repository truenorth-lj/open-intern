"""Base integration interface — all chat platform plugins implement this."""

from __future__ import annotations

import logging
import os
import uuid
from abc import ABC, abstractmethod
from typing import Any

from core.agent import OpenInternAgent
from core.telemetry import ERROR_TOTAL, PLATFORM_MESSAGE_TOTAL, set_correlation_id

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
        """Send a message to a channel or group."""
        ...

    async def send_to_user(self, user_id: str, content: str) -> None:
        """Send a direct message to a user. Default: delegates to send_message."""
        await self.send_message(channel_id=user_id, content=content)

    async def send_typing_indicator(self, event: ChatEvent) -> str | None:
        """Send a typing/thinking indicator. Returns a message_id that can be
        updated later via :meth:`update_message`, or *None* if not supported."""
        return None

    async def update_message(self, message_id: str, content: str) -> bool:
        """Update an existing message in-place. Returns True on success."""
        return False

    async def handle_event(self, event: ChatEvent) -> str | None:
        """Handle an incoming chat event. Returns the agent's response."""
        # Skip messages from the bot itself
        if self._is_self(event):
            return None

        # Set a correlation ID for this platform event
        cid = str(uuid.uuid4())
        set_correlation_id(cid)

        # Auto-capture contact from event
        try:
            await self._capture_contact(event)
        except Exception:
            logger.debug("Failed to capture contact", exc_info=True)

        # Send typing indicator (platform-specific; no-op by default)
        typing_msg_id: str | None = None
        try:
            typing_msg_id = await self.send_typing_indicator(event)
        except Exception:
            logger.debug("Typing indicator failed", exc_info=True)

        # Let the agent process it
        thread_id = event.thread_id or event.channel_id
        if not thread_id:
            logger.warning(f"No thread_id or channel_id for event from {event.platform}")

        last_exc: Exception | None = None
        try:
            response, _token_usage = await self.agent.chat(
                event.content, context=event.to_context(), thread_id=thread_id
            )
        except Exception as exc:
            logger.exception(f"Agent chat failed for event from {event.platform}")
            last_exc = exc
            ERROR_TOTAL.labels(category="platform").inc()
            _sentry_capture(exc, event)
            # Retry with a fresh thread — corrupted checkpointer state
            # (e.g. orphaned tool calls, duplicate system messages) can cause
            # persistent failures on a thread.  A fresh thread_id gives the
            # user an answer while we log the bad thread for investigation.
            if thread_id:
                fresh_thread = f"recovery-{uuid.uuid4()}"
                logger.warning(
                    "Retrying with fresh thread %s (thread_id=%s may be corrupted)",
                    fresh_thread,
                    thread_id,
                )
                PLATFORM_MESSAGE_TOTAL.labels(platform=event.platform, status="retry").inc()
                try:
                    response, _token_usage = await self.agent.chat(
                        event.content,
                        context=event.to_context(),
                        thread_id=fresh_thread,
                    )
                    last_exc = None  # retry succeeded
                except Exception as retry_exc:
                    logger.exception("Stateless retry also failed")
                    last_exc = retry_exc
                    response = None

            if not response:
                response = (
                    "Sorry, I encountered an error processing your message. Please try again."
                )
                if os.environ.get("DEBUG_BOT_ERRORS") and last_exc:
                    exc_name = type(last_exc).__name__
                    exc_msg = str(last_exc)[:200]
                    response += f"\n\n[debug: {exc_name}: {exc_msg}]"

        # Record platform message metric
        if last_exc:
            PLATFORM_MESSAGE_TOTAL.labels(platform=event.platform, status="error").inc()
        else:
            PLATFORM_MESSAGE_TOTAL.labels(platform=event.platform, status="ok").inc()

        # Send response back
        if response:
            # If we sent a typing indicator, update it in-place
            if typing_msg_id:
                updated = await self.update_message(typing_msg_id, response)
                if not updated:
                    # Fallback: send as new message if update failed
                    logger.debug("Failed to update typing message, sending new message")
                    reply_thread_id = None if event.is_dm else event.thread_id
                    await self.send_message(
                        event.channel_id,
                        response,
                        thread_id=reply_thread_id,
                    )
            else:
                # For DMs, thread_id is the chat_id (for LangGraph context), not
                # a message_id — don't pass it to the reply API.
                reply_thread_id = None if event.is_dm else event.thread_id
                await self.send_message(
                    event.channel_id,
                    response,
                    thread_id=reply_thread_id,
                )

        return response

    async def _capture_contact(self, event: ChatEvent) -> None:
        """Auto-capture user (and optionally group) from a chat event."""
        from core.messaging import upsert_contact

        database_url = getattr(self.agent, "_database_url", "")
        if not database_url:
            return

        # Capture the user
        if event.user_id and event.user_name:
            await upsert_contact(
                database_url=database_url,
                platform=event.platform,
                platform_id=event.user_id,
                contact_type="user",
                display_name=event.user_name,
            )

        # Capture the group/channel (not for DMs)
        if not event.is_dm and event.channel_id:
            await upsert_contact(
                database_url=database_url,
                platform=event.platform,
                platform_id=event.channel_id,
                contact_type="group",
                display_name=f"#{event.channel_id}",
            )

    @abstractmethod
    def _is_self(self, event: ChatEvent) -> bool:
        """Check if the event was sent by this bot."""
        ...


def _hash_id(value: str) -> str:
    """One-way hash to strip PII before sending to Sentry."""
    import hashlib

    return hashlib.sha256(value.encode()).hexdigest()[:12]


def _sentry_capture(exc: Exception, event: ChatEvent) -> None:
    """Report an exception to Sentry with platform context (no-op if disabled)."""
    try:
        from core.sentry import is_sentry_enabled

        if not is_sentry_enabled():
            return
        import sentry_sdk

        with sentry_sdk.push_scope() as scope:
            scope.set_tag("platform", event.platform)
            scope.set_tag("event_type", event.event_type)
            scope.set_context(
                "chat_event",
                {
                    "channel_id": _hash_id(event.channel_id),
                    "user_id": _hash_id(event.user_id),
                    "is_dm": event.is_dm,
                },
            )
            sentry_sdk.capture_exception(exc)
    except Exception:
        logger.warning("Sentry capture failed", exc_info=True)
