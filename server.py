"""HTTP server for the agent — webhook events, dashboard API, and platform runners."""

from __future__ import annotations

import logging
import sys

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from core.agent import OpenInternAgent
from core.config import AppConfig, load_config

logger = logging.getLogger(__name__)

# Global agent instance
_agent: OpenInternAgent | None = None


def get_agent() -> OpenInternAgent:
    if _agent is None:
        raise RuntimeError("Agent not initialized")
    return _agent


def create_app(config: AppConfig, agent: OpenInternAgent, config_path: str) -> FastAPI:
    """Create the FastAPI app with dashboard API and platform webhooks."""
    app = FastAPI(title=f"open_intern - {config.identity.name}")

    # CORS for Next.js dev server
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount dashboard API
    from api.dashboard import init_dashboard
    from api.dashboard import router as dashboard_router

    init_dashboard(agent, agent.memory_store, config, config_path)
    app.include_router(dashboard_router)

    # Health endpoint
    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "agent": config.identity.name,
            "platform": config.platform.primary,
            "memory_count": agent.memory_store.count(),
        }

    return app


def _get_port() -> int:
    """Get the server port from PORT env var (set by Zeabur/Railway) or default 8000."""
    import os

    return int(os.environ.get("PORT", "8000"))


async def run_lark(app: FastAPI, config: AppConfig, agent: OpenInternAgent) -> None:
    """Run the Lark bot with a webhook server."""
    import uvicorn

    from integrations.lark.bot import LarkBot, create_lark_webhook_handler

    bot = LarkBot(agent, config)
    await bot.start()
    handler = create_lark_webhook_handler(bot)

    @app.post("/lark/webhook")
    async def lark_webhook(request: Request):
        body = await request.json()
        return await handler(body)

    server_config = uvicorn.Config(app, host="0.0.0.0", port=_get_port(), log_level="info")
    server = uvicorn.Server(server_config)
    await server.serve()


async def run_discord(config: AppConfig, agent: OpenInternAgent) -> None:
    """Run the Discord bot."""
    from integrations.discord.bot import DiscordBot

    bot = DiscordBot(agent, config)
    await bot.start()


async def run_web_only(app: FastAPI) -> None:
    """Run only the web dashboard API (no chat platform)."""
    import uvicorn

    server_config = uvicorn.Config(app, host="0.0.0.0", port=_get_port(), log_level="info")
    server = uvicorn.Server(server_config)
    await server.serve()


async def run_agent(config_path: str | None = None) -> None:
    """Main entry point — initialize and run the agent on the configured platform."""
    global _agent

    config = load_config(config_path)

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logger.info(f"Starting open_intern agent: {config.identity.name}")
    logger.info(f"Platform: {config.platform.primary}")
    logger.info(f"LLM: {config.llm.provider}:{config.llm.model}")

    # Initialize agent
    agent = OpenInternAgent(config)
    agent.initialize()
    _agent = agent

    # Create the shared FastAPI app
    app = create_app(config, agent, config_path or "config/agent.yaml")

    # Run on the configured platform
    platform = config.platform.primary
    if platform == "lark":
        await run_lark(app, config, agent)
    elif platform == "discord":
        await run_discord(config, agent)
    elif platform == "web":
        logger.info("Running in web-only mode (dashboard API on port 8000)")
        await run_web_only(app)
    elif platform == "slack":
        logger.error("Slack integration not yet implemented. Use lark, discord, or web.")
        sys.exit(1)
    else:
        logger.error(f"Unknown platform: {platform}")
        sys.exit(1)
