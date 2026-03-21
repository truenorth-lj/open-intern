"""HTTP server for the agent — webhook events, dashboard API, and platform runners."""

from __future__ import annotations

import logging
import sys

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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

    # CORS for Next.js dev server and Zeabur frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "https://open-intern.zeabur.app"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API key authentication middleware
    api_secret = config.api_secret_key

    @app.middleware("http")
    async def check_api_key(request: Request, call_next):
        # Skip auth for health endpoint and if no secret is configured
        if not api_secret or request.url.path == "/health":
            return await call_next(request)
        key = request.headers.get("X-API-Key", "")
        if key != api_secret:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
        return await call_next(request)

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
            "platform": config.active_platform,
            "memory_count": agent.memory_store.count(),
        }

    return app


def _get_port(config: AppConfig) -> int:
    """Get the server port from config (PORT env var auto-mapped by pydantic-settings)."""
    return config.port


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

    server_config = uvicorn.Config(app, host="0.0.0.0", port=_get_port(config), log_level="info")
    server = uvicorn.Server(server_config)
    await server.serve()


async def run_discord(config: AppConfig, agent: OpenInternAgent) -> None:
    """Run the Discord bot."""
    from integrations.discord.bot import DiscordBot

    bot = DiscordBot(agent, config)
    await bot.start()


async def run_telegram(app: FastAPI, config: AppConfig, agent: OpenInternAgent) -> None:
    """Run the Telegram bot alongside the web dashboard."""
    import asyncio

    import uvicorn

    from integrations.telegram.bot import TelegramBot

    bot = TelegramBot(agent, config)

    server_config = uvicorn.Config(app, host="0.0.0.0", port=_get_port(config), log_level="info")
    server = uvicorn.Server(server_config)

    # Run both the web server and telegram bot concurrently
    await asyncio.gather(server.serve(), bot.start())


async def run_web_only(app: FastAPI, config: AppConfig) -> None:
    """Run only the web dashboard API (no chat platform)."""
    import uvicorn

    server_config = uvicorn.Config(app, host="0.0.0.0", port=_get_port(config), log_level="info")
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

    platform = config.active_platform
    logger.info(f"Starting open_intern agent: {config.identity.name}")
    logger.info(f"Platform: {platform}")
    logger.info(f"LLM: {config.llm.provider}:{config.llm.model}")

    # Initialize agent
    agent = OpenInternAgent(config)
    agent.initialize()
    _agent = agent

    # Create the shared FastAPI app
    app = create_app(config, agent, config_path or "config/agent.yaml")

    # Run on the configured platform
    if platform == "lark":
        await run_lark(app, config, agent)
    elif platform == "discord":
        await run_discord(config, agent)
    elif platform == "web":
        logger.info(f"Running in web-only mode (dashboard API on port {config.port})")
        await run_web_only(app, config)
    elif platform == "telegram":
        await run_telegram(app, config, agent)
    elif platform == "slack":
        logger.error("Slack integration not yet implemented. Use lark, discord, or web.")
        sys.exit(1)
    else:
        logger.error(f"Unknown platform: {platform}")
        sys.exit(1)
