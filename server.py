"""HTTP server — webhook endpoints, dashboard API, and multi-agent management."""

from __future__ import annotations

import logging
import os
import sys

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.agent import OpenInternAgent
from core.config import AppConfig, load_config
from core.manager import AgentManager

logger = logging.getLogger(__name__)

# Global state
_agent_manager: AgentManager | None = None
# Legacy single-agent reference (for backward compat with dashboard)
_default_agent: OpenInternAgent | None = None
# Telegram bots keyed by agent_id
_telegram_bots: dict = {}


def get_agent_manager() -> AgentManager:
    if _agent_manager is None:
        raise RuntimeError("Agent manager not initialized")
    return _agent_manager


def get_agent(agent_id: str | None = None) -> OpenInternAgent:
    """Get an agent by ID, or the default agent."""
    mgr = get_agent_manager()
    if agent_id:
        agent = mgr.get(agent_id)
        if agent:
            return agent
    # Fallback to default (first active agent or legacy single agent)
    if _default_agent:
        return _default_agent
    # Return first available agent
    agents = mgr.agents
    if agents:
        return next(iter(agents.values()))
    raise RuntimeError("No agents available")


def create_app(config: AppConfig, config_path: str) -> FastAPI:
    """Create the FastAPI app with dashboard API, agent CRUD, and webhook endpoints."""
    app = FastAPI(title="open_intern — multi-agent")

    # CORS
    default_origins = ["http://localhost:3000", "https://open-intern.zeabur.app"]
    env_origins = os.environ.get("CORS_ORIGINS")
    if env_origins is not None:
        cors_origins = [o.strip() for o in env_origins.split(",") if o.strip()]
    else:
        cors_origins = default_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API key authentication middleware
    api_secret = config.api_secret_key

    @app.middleware("http")
    async def check_api_key(request: Request, call_next):
        if not api_secret or request.url.path in ("/health", "/docs", "/openapi.json"):
            return await call_next(request)
        # Allow webhook endpoints without API key (Telegram sends updates directly)
        if request.url.path.startswith("/webhook/"):
            return await call_next(request)
        key = request.headers.get("X-API-Key", "")
        if key != api_secret:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
        return await call_next(request)

    # Mount dashboard API
    from api.dashboard import init_dashboard
    from api.dashboard import router as dashboard_router

    init_dashboard(config, config_path)
    app.include_router(dashboard_router)

    # --- Telegram webhook endpoints ---

    @app.post("/webhook/{agent_id}")
    async def telegram_webhook(agent_id: str, request: Request):
        """Receive Telegram updates for a specific agent."""
        bot = _telegram_bots.get(agent_id)
        if not bot:
            return JSONResponse(
                status_code=404,
                content={"detail": f"No bot for agent '{agent_id}'"},
            )
        update_data = await request.json()

        # Process in background so we return 200 quickly to Telegram
        import asyncio

        async def _safe_process():
            try:
                await bot.process_update(update_data)
            except Exception:
                logger.exception(f"Failed to process Telegram update for agent '{agent_id}'")

        asyncio.create_task(_safe_process())
        return {"ok": True}

    # Health endpoint
    @app.get("/health")
    async def health():
        mgr = _agent_manager
        agent_count = len(mgr.agents) if mgr else 0
        bot_count = len(_telegram_bots)
        return {
            "status": "ok",
            "agents": agent_count,
            "telegram_bots": bot_count,
        }

    return app


def _get_port(config: AppConfig) -> int:
    return config.port


async def _setup_telegram_webhooks(config: AppConfig, manager: AgentManager) -> None:
    """Start Telegram bots and register webhooks for all agents with tokens."""
    from integrations.telegram.bot import TelegramBot

    # Determine the public base URL for webhooks
    webhook_base = os.environ.get("WEBHOOK_BASE_URL", "").rstrip("/")
    if not webhook_base:
        port = _get_port(config)
        webhook_base = f"https://localhost:{port}"
        logger.warning(
            f"WEBHOOK_BASE_URL not set. Using {webhook_base}. "
            "Set WEBHOOK_BASE_URL to your public HTTPS domain for production."
        )

    tg_agents = manager.get_telegram_agents()
    for agent_id, record in tg_agents.items():
        agent = manager.get(agent_id)
        if not agent:
            logger.warning(f"Agent {agent_id} has Telegram token but is not initialized")
            continue
        try:
            bot = TelegramBot(agent, token=record.telegram_token, agent_id=agent_id)
            await bot.start()
            webhook_url = f"{webhook_base}/webhook/{agent_id}"
            await bot.setup_webhook(webhook_url)
            _telegram_bots[agent_id] = bot
        except Exception as e:
            logger.error(f"Failed to setup Telegram bot for agent {agent_id}: {e}")


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


async def run_web_only(app: FastAPI, config: AppConfig) -> None:
    """Run only the web dashboard API (no chat platform)."""
    import uvicorn

    server_config = uvicorn.Config(app, host="0.0.0.0", port=_get_port(config), log_level="info")
    server = uvicorn.Server(server_config)
    await server.serve()


async def run_agent(config_path: str | None = None) -> None:
    """Main entry point — initialize agent manager and run on configured platform."""
    global _agent_manager, _default_agent

    config = load_config(config_path)

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    platform = config.active_platform
    logger.info(f"Starting open_intern (platform: {platform})")

    # Initialize agent manager (loads all agents from DB)
    manager = AgentManager(config)
    manager.initialize()
    _agent_manager = manager

    # If no agents in DB, create a default agent from config (backward compat)
    if not manager.agents:
        logger.info("No agents in DB — creating default agent from config")
        agent = OpenInternAgent(config, agent_id="default")
        agent.initialize()
        _default_agent = agent
        manager._agents["default"] = agent

    # Create the FastAPI app
    app = create_app(config, config_path or "config/agent.yaml")

    # Run on the configured platform
    if platform == "telegram":
        # Setup Telegram webhooks for all agents with tokens
        await _setup_telegram_webhooks(config, manager)
        # Also support the legacy single-bot mode via env var
        if not _telegram_bots and config.effective_telegram_token:
            from integrations.telegram.bot import TelegramBot

            default_agent = get_agent()
            webhook_base = os.environ.get("WEBHOOK_BASE_URL", "").rstrip("/")
            bot = TelegramBot(
                default_agent,
                token=config.effective_telegram_token,
                agent_id="default",
            )
            await bot.start()
            if webhook_base:
                await bot.setup_webhook(f"{webhook_base}/webhook/default")
            _telegram_bots["default"] = bot
        # Start the web server
        await run_web_only(app, config)
    elif platform == "lark":
        default_agent = get_agent()
        await run_lark(app, config, default_agent)
    elif platform == "discord":
        default_agent = get_agent()
        await run_discord(config, default_agent)
    elif platform == "web":
        logger.info(f"Running in web-only mode (dashboard API on port {config.port})")
        await run_web_only(app, config)
    elif platform == "slack":
        logger.error("Slack integration not yet implemented.")
        sys.exit(1)
    else:
        logger.error(f"Unknown platform: {platform}")
        sys.exit(1)
