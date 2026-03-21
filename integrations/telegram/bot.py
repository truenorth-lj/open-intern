"""Telegram bot integration using python-telegram-bot."""

from __future__ import annotations

import logging

from core.agent import OpenInternAgent
from core.config import AppConfig
from integrations.base import ChatEvent, Integration

logger = logging.getLogger(__name__)


class TelegramBot(Integration):
    """Telegram bot integration using python-telegram-bot."""

    def __init__(self, agent: OpenInternAgent, config: AppConfig):
        super().__init__(agent)
        token = config.effective_telegram_token
        if not token.strip():
            raise ValueError(
                "Telegram bot_token is required. Set TELEGRAM_BOT_TOKEN in .env "
                "or platform.telegram.bot_token in config/agent.yaml"
            )
        self.token = token
        self._app = None
        self._bot_id: str = ""
        self._bot_username: str = ""

    async def start(self) -> None:
        """Start the Telegram bot (long polling)."""
        try:
            from telegram import Update
            from telegram.ext import (
                ApplicationBuilder,
                CommandHandler,
                MessageHandler,
                filters,
            )
        except ImportError:
            raise ImportError(
                "python-telegram-bot is required for Telegram integration. "
                "Install with: pip install 'open-intern[telegram]'"
            )

        app = ApplicationBuilder().token(self.token).build()
        self._app = app

        async def on_start(update: Update, context):
            """Handle /start command."""
            await update.message.reply_text(
                "Hi! I'm your AI employee. Send me a message or mention me in a group."
            )

        async def on_message(update: Update, context):
            """Handle incoming messages."""
            message = update.message
            if not message or not message.text:
                return

            # Get bot info on first message
            if not self._bot_id:
                bot_info = await app.bot.get_me()
                self._bot_id = str(bot_info.id)
                self._bot_username = bot_info.username or ""

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
            event = ChatEvent(
                platform="telegram",
                event_type="message",
                channel_id=str(message.chat_id),
                user_id=str(user.id) if user else "unknown",
                user_name=(user.full_name if user else "Unknown"),
                content=content,
                is_dm=is_private,
                thread_id=str(message.message_id),
                raw=update,
            )

            # Show "typing..." indicator while processing (re-send every 4s)
            import asyncio

            typing_active = True

            async def keep_typing():
                while typing_active:
                    await message.chat.send_action("typing")
                    await asyncio.sleep(4)

            typing_task = asyncio.create_task(keep_typing())
            try:
                await self.handle_event(event)
            finally:
                typing_active = False
                typing_task.cancel()

        app.add_handler(CommandHandler("start", on_start))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

        logger.info("Starting Telegram bot (polling)...")
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)

        # Keep running until stopped
        import asyncio

        stop_event = asyncio.Event()
        self._stop_event = stop_event
        await stop_event.wait()

    async def stop(self) -> None:
        """Stop the Telegram bot."""
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            logger.info("Telegram bot stopped")
        if hasattr(self, "_stop_event"):
            self._stop_event.set()

    async def send_message(
        self, channel_id: str, content: str, thread_id: str | None = None
    ) -> None:
        """Send a message to a Telegram chat."""
        if not self._app:
            logger.error("Telegram bot not started")
            return

        # Telegram has 4096 char limit
        if len(content) <= 4096:
            await self._app.bot.send_message(
                chat_id=int(channel_id),
                text=content,
                reply_to_message_id=int(thread_id) if thread_id else None,
            )
        else:
            chunks = [content[i : i + 4000] for i in range(0, len(content), 4000)]
            for i, chunk in enumerate(chunks):
                await self._app.bot.send_message(
                    chat_id=int(channel_id),
                    text=chunk,
                    reply_to_message_id=int(thread_id) if i == 0 and thread_id else None,
                )

    def _is_self(self, event: ChatEvent) -> bool:
        return event.user_id == self._bot_id
