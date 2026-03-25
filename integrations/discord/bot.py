"""Discord bot integration."""

from __future__ import annotations

import logging

from core.agent import OpenInternAgent
from integrations.base import ChatEvent, Integration
from integrations.utils import chunk_message

logger = logging.getLogger(__name__)


class DiscordBot(Integration):
    """Discord bot integration using discord.py."""

    def __init__(self, agent: OpenInternAgent, token: str):
        super().__init__(agent)
        self.token = token
        self._bot = None
        self._bot_id: str = ""

    async def start(self) -> None:
        """Start the Discord bot."""
        try:
            import discord
        except ImportError:
            raise ImportError(
                "discord.py is required for Discord integration. "
                "Install with: pip install 'open-intern[discord]'"
            )

        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True

        client = discord.Client(intents=intents)
        self._bot = client

        @client.event
        async def on_ready():
            self._bot_id = str(client.user.id)
            logger.info(f"Discord bot ready: {client.user.name} ({self._bot_id})")

        @client.event
        async def on_message(message: discord.Message):
            # Skip own messages
            if message.author.id == client.user.id:
                return

            # Check if bot is mentioned or it's a DM
            is_mentioned = client.user in message.mentions
            is_dm = isinstance(message.channel, discord.DMChannel)

            if not is_mentioned and not is_dm:
                return

            # Strip the mention from content
            content = message.content
            if is_mentioned:
                content = content.replace(f"<@{client.user.id}>", "").strip()

            event = ChatEvent(
                platform="discord",
                event_type="message",
                channel_id=str(message.channel.id),
                user_id=str(message.author.id),
                user_name=message.author.display_name,
                content=content,
                is_dm=is_dm,
                thread_id=str(message.id),
                raw=message,
            )

            await self.handle_event(event)

        # Run the bot (this blocks)
        logger.info("Starting Discord bot...")
        await client.start(self.token)

    async def stop(self) -> None:
        """Stop the Discord bot."""
        if self._bot:
            await self._bot.close()
            logger.info("Discord bot stopped")

    async def send_message(
        self, channel_id: str, content: str, thread_id: str | None = None
    ) -> None:
        """Send a message to a Discord channel."""
        if not self._bot:
            logger.error("Discord bot not started")
            return

        channel = self._bot.get_channel(int(channel_id))
        if channel is None:
            logger.error(f"Channel {channel_id} not found")
            return

        for chunk in chunk_message(content, max_size=2000):
            await channel.send(chunk)

    async def send_to_user(self, user_id: str, content: str) -> None:
        """Send a DM to a Discord user."""
        if not self._bot:
            logger.error("Discord bot not started")
            return

        try:
            user = await self._bot.fetch_user(int(user_id))
            for chunk in chunk_message(content, max_size=2000):
                await user.send(chunk)
            logger.debug(f"DM sent to Discord user {user_id}")
        except Exception:
            logger.exception(f"Failed to send Discord DM to {user_id}")

    def _is_self(self, event: ChatEvent) -> bool:
        return event.user_id == self._bot_id
