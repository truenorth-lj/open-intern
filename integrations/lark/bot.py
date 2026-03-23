"""Lark (Feishu) bot integration using lark-oapi SDK with WebSocket persistent connection."""

from __future__ import annotations

import asyncio
import json
import logging
import threading

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

    async def _fetch_bot_open_id(self) -> None:
        """Fetch the bot's own open_id to filter self-messages."""
        try:
            import lark_oapi.api.bot.v3 as bot_v3

            request = bot_v3.GetBotInfoRequest.builder().build()
            response = await asyncio.to_thread(self._api_client.bot.v3.bot_info.get, request)
            if response.success() and response.data and response.data.bot:
                self._bot_open_id = response.data.bot.open_id or ""
                logger.info(f"Lark bot open_id: {self._bot_open_id}")
            else:
                logger.warning(f"Failed to fetch bot info: {getattr(response, 'msg', 'unknown')}")
        except Exception:
            logger.warning(
                "Could not fetch bot open_id, self-message filtering disabled",
                exc_info=True,
            )

    async def start(self) -> None:
        """Start the WebSocket connection in a background thread."""
        self._loop = asyncio.get_running_loop()
        await self._fetch_bot_open_id()

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
        """Stop the WebSocket connection and clean up."""
        if hasattr(self._ws_client, "stop"):
            try:
                self._ws_client.stop()
            except Exception:
                logger.debug("Error stopping ws client", exc_info=True)
        if self._ws_thread and self._ws_thread.is_alive():
            self._ws_thread.join(timeout=5)
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
                    ReplyMessageRequestBody.builder().msg_type("text").content(text_content).build()
                )
                .build()
            )
            response = await asyncio.to_thread(self._api_client.im.v1.message.reply, request)
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
            response = await asyncio.to_thread(self._api_client.im.v1.message.create, request)

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
            # Lark field mapping: open_id is the stable user identifier,
            # user_id is a human-readable ID (not a display name).
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
                future = asyncio.run_coroutine_threadsafe(self.handle_event(chat_event), self._loop)
                future.add_done_callback(
                    lambda f: logger.exception("Error in handle_event", exc_info=f.exception())
                    if f.exception()
                    else None
                )
            else:
                logger.warning("Event loop not available, dropping message")

        except Exception:
            logger.exception("Error handling Lark message event")
