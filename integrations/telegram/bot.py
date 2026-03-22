"""Telegram bot integration — webhook mode with multi-agent support."""

from __future__ import annotations

import logging
import time
from uuid import uuid4

from core.agent import OpenInternAgent
from integrations.base import ChatEvent, Integration

logger = logging.getLogger(__name__)


class TelegramBot(Integration):
    """Telegram bot integration using webhook mode."""

    # Minimum seconds between message edits to avoid Telegram API rate limits
    EDIT_INTERVAL_SECONDS = 1.5

    def __init__(self, agent: OpenInternAgent, token: str, agent_id: str):
        super().__init__(agent)
        if not token.strip():
            raise ValueError(f"Telegram bot token is required for agent '{agent_id}'")
        self.token = token
        self.agent_id = agent_id
        self._app = None
        self._bot_id: str = ""
        self._bot_username: str = ""
        self.webhook_secret: str = ""
        # Thread management: chat_id -> current thread_id
        self._threads: dict[int, str] = {}

    def _get_thread_id(self, chat_id: int) -> str:
        """Get current thread_id for a chat, creating one if needed."""
        if chat_id not in self._threads:
            self._threads[chat_id] = f"tg-{self.agent_id}-{chat_id}-{uuid4().hex[:8]}"
        return self._threads[chat_id]

    def _reset_thread(self, chat_id: int) -> str:
        """Reset thread for a chat, returning the new thread_id."""
        self._threads[chat_id] = f"tg-{self.agent_id}-{chat_id}-{uuid4().hex[:8]}"
        return self._threads[chat_id]

    async def start(self) -> None:
        """Initialize the bot application (no polling — webhook only)."""
        try:
            from telegram.ext import ApplicationBuilder
        except ImportError:
            raise ImportError(
                "python-telegram-bot is required for Telegram integration. "
                "Install with: pip install 'open-intern[telegram]'"
            )

        self._app = ApplicationBuilder().token(self.token).build()
        await self._app.initialize()
        await self._app.start()

        # Fetch bot info
        bot_info = await self._app.bot.get_me()
        self._bot_id = str(bot_info.id)
        self._bot_username = bot_info.username or ""
        logger.info(f"Telegram bot ready: @{self._bot_username} (agent: {self.agent_id})")

    async def setup_webhook(self, webhook_url: str) -> None:
        """Register the webhook URL with Telegram API."""
        if not self._app:
            raise RuntimeError("Bot not started. Call start() first.")
        # Generate a secret token for webhook verification
        self.webhook_secret = uuid4().hex
        await self._app.bot.set_webhook(
            url=webhook_url,
            drop_pending_updates=True,
            secret_token=self.webhook_secret,
        )
        logger.info(f"Webhook set for @{self._bot_username}: {webhook_url}")

    async def process_update(self, update_data: dict) -> None:
        """Process a single webhook update from Telegram."""
        if not self._app:
            return

        from telegram import Update

        update = Update.de_json(update_data, self._app.bot)
        if not update:
            return

        message = update.message
        if not message or not message.text:
            return

        # Handle /start command
        if message.text.strip() == "/start":
            await message.reply_text(
                f"Hi! I'm {self.agent.config.identity.name}. "
                "Send me a message or mention me in a group.\n"
                "Use /new to start a fresh conversation."
            )
            return

        # Handle /new command
        if message.text.strip() == "/new":
            self._reset_thread(message.chat_id)
            await message.reply_text("Conversation reset. Starting a fresh thread.")
            return

        # In groups, only respond when mentioned or replied to
        is_private = message.chat.type == "private"
        is_mentioned = self._bot_username and f"@{self._bot_username}" in (message.text or "")
        is_reply_to_bot = (
            message.reply_to_message
            and message.reply_to_message.from_user
            and str(message.reply_to_message.from_user.id) == self._bot_id
        )

        if not is_private and not is_mentioned and not is_reply_to_bot:
            return

        # Strip bot mention from content
        content = message.text
        if is_mentioned and self._bot_username:
            content = content.replace(f"@{self._bot_username}", "").strip()

        user = message.from_user
        thread_id = self._get_thread_id(message.chat_id)
        event = ChatEvent(
            platform="telegram",
            event_type="message",
            channel_id=str(message.chat_id),
            user_id=str(user.id) if user else "unknown",
            user_name=(user.full_name if user else "Unknown"),
            content=content,
            is_dm=is_private,
            thread_id=thread_id,
            raw=update,
        )

        # Stream response with progressive message editing
        await self._handle_event_stream(event, message)

    async def _handle_event_stream(self, event: ChatEvent, tg_message) -> None:
        """Stream agent response, progressively editing a Telegram message."""
        if self._is_self(event):
            return

        thread_id = event.thread_id or event.channel_id
        chat_id = int(event.channel_id)

        # Send initial "Thinking..." message
        sent = await self._app.bot.send_message(chat_id=chat_id, text="Thinking...")
        accumulated = ""
        last_edit = 0.0

        try:
            async for chunk in self.agent.chat_stream(
                event.content, context=event.to_context(), thread_id=thread_id
            ):
                if chunk["type"] == "token":
                    accumulated += chunk["content"]
                    now = time.monotonic()
                    # Rate-limit edits to avoid Telegram API throttling
                    if now - last_edit >= self.EDIT_INTERVAL_SECONDS and accumulated:
                        try:
                            display = accumulated[:4096]
                            await self._app.bot.edit_message_text(
                                chat_id=chat_id,
                                message_id=sent.message_id,
                                text=display,
                            )
                            last_edit = now
                        except Exception:
                            pass  # edit may fail if text unchanged

                elif chunk["type"] == "done":
                    accumulated = chunk.get("content", accumulated)

        except Exception:
            logger.exception("Streaming failed for Telegram event")
            if not accumulated:
                accumulated = "Sorry, an error occurred while processing your message."

        # Final edit with complete response
        if accumulated:
            if len(accumulated) <= 4096:
                try:
                    await self._app.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=sent.message_id,
                        text=accumulated,
                    )
                except Exception:
                    pass
            else:
                # Delete the partial message, send full response in chunks
                try:
                    await self._app.bot.delete_message(chat_id=chat_id, message_id=sent.message_id)
                except Exception:
                    pass
                await self.send_message(event.channel_id, accumulated)

    async def stop(self) -> None:
        """Stop the Telegram bot and remove webhook."""
        if self._app:
            try:
                await self._app.bot.delete_webhook()
            except Exception:
                pass
            await self._app.stop()
            await self._app.shutdown()
            logger.info(f"Telegram bot stopped: @{self._bot_username}")

    async def send_message(
        self, channel_id: str, content: str, thread_id: str | None = None
    ) -> None:
        """Send a message to a Telegram chat."""
        if not self._app:
            logger.error("Telegram bot not started")
            return

        # Telegram has 4096 char limit
        if len(content) <= 4096:
            await self._app.bot.send_message(chat_id=int(channel_id), text=content)
        else:
            chunks = [content[i : i + 4000] for i in range(0, len(content), 4000)]
            for chunk in chunks:
                await self._app.bot.send_message(chat_id=int(channel_id), text=chunk)

    def _is_self(self, event: ChatEvent) -> bool:
        return event.user_id == self._bot_id
