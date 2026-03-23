"""Lark (Feishu) bot integration using lark-oapi SDK with WebSocket persistent connection."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Any

import lark_oapi as lark
from lark_oapi import ws as lark_ws
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    P2ImMessageReceiveV1,
    ReplyMessageRequest,
    ReplyMessageRequestBody,
)

from core.agent import OpenInternAgent
from integrations.base import ChatEvent, Integration

logger = logging.getLogger(__name__)

# Domain constants
LARK_DOMAIN = lark.LARK_DOMAIN
FEISHU_DOMAIN = lark.FEISHU_DOMAIN


class LarkBot(Integration):
    """Lark/Feishu bot integration using WebSocket persistent connection."""

    def __init__(
        self,
        agent: OpenInternAgent,
        app_id: str,
        app_secret: str,
        domain: str = "",
    ):
        super().__init__(agent)
        self.app_id = app_id
        self.app_secret = app_secret
        self._domain = domain or LARK_DOMAIN
        self._bot_open_id: str = ""
        self._ws_thread: threading.Thread | None = None

        # API client for sending messages
        self._api_client = (
            lark.Client.builder()
            .app_id(app_id)
            .app_secret(app_secret)
            .domain(self._domain)
            .log_level(lark.LogLevel.INFO)
            .build()
        )

        # Event dispatcher (will be wired to _on_message_receive)
        self._event_handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self._on_message_receive)
            .build()
        )

        # WebSocket client
        self._ws_client = lark_ws.Client(
            app_id=app_id,
            app_secret=app_secret,
            event_handler=self._event_handler,
            log_level=lark.LogLevel.INFO,
            domain=self._domain,
            auto_reconnect=True,
        )

        # Event loop for running async agent code from sync callback
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self) -> None:
        """Start the WebSocket connection in a background thread."""
        self._loop = asyncio.get_running_loop()

        def _run_ws() -> None:
            """Run ws.Client.start() in a fresh event loop.

            The lark_oapi.ws.client module captures the event loop at import
            time into a module-level ``loop`` variable and uses it inside
            ``start()``.  We must patch that variable so it points to our
            fresh loop instead of the main asyncio loop (which is already
            running and would raise "This event loop is already running").
            """
            import lark_oapi.ws.client as ws_mod

            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            ws_mod.loop = new_loop
            # Also recreate the lock on the new loop
            self._ws_client._lock = asyncio.Lock()
            try:
                self._ws_client.start()
            finally:
                new_loop.close()

        # Start WebSocket client in a daemon thread (ws.Client.start() blocks)
        self._ws_thread = threading.Thread(
            target=_run_ws,
            name="lark-ws",
            daemon=True,
        )
        self._ws_thread.start()
        logger.info("Lark bot started (WebSocket persistent connection)")

    async def stop(self) -> None:
        """Stop the bot."""
        logger.info("Lark bot stopped")

    async def send_message(
        self, channel_id: str, content: str, thread_id: str | None = None
    ) -> None:
        """Send a text message to a Lark chat."""
        text_content = json.dumps({"text": content})

        if thread_id:
            # Reply in thread
            request = (
                ReplyMessageRequest.builder()
                .message_id(thread_id)
                .request_body(
                    ReplyMessageRequestBody.builder()
                    .msg_type("text")
                    .content(text_content)
                    .build()
                )
                .build()
            )
            response = await asyncio.to_thread(
                self._api_client.im.v1.message.reply, request
            )
        else:
            request = (
                CreateMessageRequest.builder()
                .receive_id_type("chat_id")
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(channel_id)
                    .msg_type("text")
                    .content(text_content)
                    .build()
                )
                .build()
            )
            response = await asyncio.to_thread(
                self._api_client.im.v1.message.create, request
            )

        if not response.success():
            logger.error(f"Failed to send Lark message: {response.code} - {response.msg}")
        else:
            logger.debug(f"Message sent to {channel_id}")

    def _is_self(self, event: ChatEvent) -> bool:
        return event.user_id == self._bot_open_id

    def _on_message_receive(self, data: P2ImMessageReceiveV1) -> None:
        """Sync callback invoked by the SDK when a message is received."""
        try:
            message = data.event.message
            sender = data.event.sender

            # Parse message content
            content_data = json.loads(message.content)
            text = content_data.get("text", "")
            if not text:
                return

            chat_type = message.chat_type or ""
            chat_event = ChatEvent(
                platform="lark",
                event_type="message",
                channel_id=message.chat_id or "",
                user_id=sender.sender_id.open_id or "",
                user_name=sender.sender_id.user_id or "unknown",
                content=text,
                is_dm=(chat_type == "p2p"),
                thread_id=getattr(message, "root_id", None) or message.message_id,
                raw=data,
            )

            # Skip self messages
            if self._is_self(chat_event):
                return

            # Schedule async handle_event on the main event loop
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(self.handle_event(chat_event), self._loop)
            else:
                logger.warning("Event loop not available, dropping message")

        except Exception:
            logger.exception("Error handling Lark message event")

    def parse_event(self, event_body: dict[str, Any]) -> ChatEvent | None:
        """Parse a raw Lark event dict into a ChatEvent (for testing/compat)."""
        header = event_body.get("header", {})
        event = event_body.get("event", {})
        event_type = header.get("event_type", "")

        if event_type == "im.message.receive_v1":
            message = event.get("message", {})
            sender = event.get("sender", {}).get("sender_id", {})
            chat_type = message.get("chat_type", "")

            content_str = message.get("content", "{}")
            try:
                content_data = json.loads(content_str)
                text = content_data.get("text", "")
            except (json.JSONDecodeError, TypeError):
                text = content_str

            if not text:
                return None

            return ChatEvent(
                platform="lark",
                event_type="message",
                channel_id=message.get("chat_id", ""),
                user_id=sender.get("open_id", ""),
                user_name=sender.get("user_id", "unknown"),
                content=text,
                is_dm=(chat_type == "p2p"),
                thread_id=message.get("root_id") or message.get("message_id"),
                raw=event_body,
            )

        return None
