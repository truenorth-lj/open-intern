"""Lark (Feishu) bot integration."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from core.agent import OpenInternAgent
from core.config import AppConfig
from integrations.base import ChatEvent, Integration

logger = logging.getLogger(__name__)

# Lark Open API base URL
LARK_API = "https://open.larksuite.com/open-apis"
FEISHU_API = "https://open.feishu.cn/open-apis"


class LarkBot(Integration):
    """Lark/Feishu bot integration using Open API."""

    def __init__(self, agent: OpenInternAgent, config: AppConfig):
        super().__init__(agent)
        self.app_id = config.platform_config.lark.app_id
        self.app_secret = config.platform_config.lark.app_secret
        self._tenant_access_token: str = ""
        self._bot_id: str = ""
        self._running = False
        # Use Feishu API for China, Lark API for international
        self._api_base = FEISHU_API
        self._client = httpx.AsyncClient(timeout=30)

    async def _get_tenant_token(self) -> str:
        """Get tenant access token from Lark API."""
        resp = await self._client.post(
            f"{self._api_base}/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
        )
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Failed to get Lark token: {data}")
        self._tenant_access_token = data["tenant_access_token"]
        logger.info("Lark tenant access token acquired")
        return self._tenant_access_token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._tenant_access_token}",
            "Content-Type": "application/json; charset=utf-8",
        }

    async def _get_bot_info(self) -> None:
        """Get bot's own user ID."""
        resp = await self._client.get(
            f"{self._api_base}/bot/v3/info",
            headers=self._headers(),
        )
        data = resp.json()
        if data.get("code") == 0:
            self._bot_id = data.get("bot", {}).get("open_id", "")
            bot_name = data.get("bot", {}).get("app_name", "unknown")
            logger.info(f"Lark bot identified: {bot_name} ({self._bot_id})")

    async def start(self) -> None:
        """Start the Lark bot with long-polling for events.

        Note: For production, you'd use Lark's webhook/websocket event subscription.
        This implementation uses a polling approach for simplicity.
        In production, set up an HTTP server to receive Lark event callbacks.
        """
        await self._get_tenant_token()
        await self._get_bot_info()
        self._running = True
        logger.info("Lark bot started. Listening for events...")

    async def stop(self) -> None:
        """Stop the bot."""
        self._running = False
        await self._client.aclose()
        logger.info("Lark bot stopped")

    async def send_message(
        self, channel_id: str, content: str, thread_id: str | None = None
    ) -> None:
        """Send a message to a Lark chat."""
        # Refresh token if needed
        if not self._tenant_access_token:
            await self._get_tenant_token()

        payload: dict[str, Any] = {
            "receive_id": channel_id,
            "msg_type": "text",
            "content": f'{{"text": "{content}"}}',
        }

        receive_id_type = "chat_id"

        url = f"{self._api_base}/im/v1/messages?receive_id_type={receive_id_type}"

        if thread_id:
            # Reply in thread
            url = f"{self._api_base}/im/v1/messages/{thread_id}/reply"
            payload = {
                "msg_type": "text",
                "content": f'{{"text": "{content}"}}',
            }

        resp = await self._client.post(url, headers=self._headers(), json=payload)
        data = resp.json()
        if data.get("code") != 0:
            logger.error(f"Failed to send Lark message: {data}")
        else:
            logger.debug(f"Message sent to {channel_id}")

    def _is_self(self, event: ChatEvent) -> bool:
        return event.user_id == self._bot_id

    def parse_event(self, event_body: dict[str, Any]) -> ChatEvent | None:
        """Parse a Lark event callback into a ChatEvent."""
        header = event_body.get("header", {})
        event = event_body.get("event", {})
        event_type = header.get("event_type", "")

        if event_type == "im.message.receive_v1":
            message = event.get("message", {})
            sender = event.get("sender", {}).get("sender_id", {})
            chat_type = message.get("chat_type", "")

            # Parse message content
            content_str = message.get("content", "{}")
            try:
                import json

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


def create_lark_webhook_handler(bot: LarkBot):
    """Create an HTTP handler for Lark event callbacks.

    Returns a handler function that can be used with any ASGI/WSGI framework.
    Example with FastAPI:

        from fastapi import FastAPI, Request
        app = FastAPI()
        handler = create_lark_webhook_handler(bot)

        @app.post("/lark/webhook")
        async def lark_webhook(request: Request):
            body = await request.json()
            return await handler(body)
    """

    async def handle(body: dict[str, Any]) -> dict[str, Any]:
        # URL verification challenge
        if "challenge" in body:
            return {"challenge": body["challenge"]}

        # Parse and handle the event
        event = bot.parse_event(body)
        if event:
            await bot.handle_event(event)

        return {"code": 0}

    return handle
