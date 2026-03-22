"""HTTP server — webhook endpoints, dashboard API, and multi-agent management."""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.agent import OpenInternAgent
from core.config import AppConfig, get_config
from core.manager import AgentManager
from core.scheduler import CronScheduler

logger = logging.getLogger(__name__)

# Global state
_agent_manager: AgentManager | None = None
_cron_scheduler: CronScheduler | None = None
# Legacy single-agent reference (for backward compat with dashboard)
_default_agent: OpenInternAgent | None = None
# Platform bots keyed by agent_id
_telegram_bots: dict = {}
_discord_bots: dict = {}


def get_agent_manager() -> AgentManager:
    if _agent_manager is None:
        raise RuntimeError("Agent manager not initialized")
    return _agent_manager


def get_cron_scheduler() -> CronScheduler:
    if _cron_scheduler is None:
        raise RuntimeError("Cron scheduler not initialized")
    return _cron_scheduler


def get_bot(platform: str, agent_id: str) -> Any | None:
    """Get a platform bot instance for outbound messaging."""
    if platform == "telegram":
        bot = _telegram_bots.get(agent_id)
        if bot:
            return bot
        return _telegram_bots.get("default")
    if platform == "discord":
        bot = _discord_bots.get(agent_id)
        if bot:
            return bot
        return _discord_bots.get("default")
    logger.warning(f"Unsupported delivery platform: {platform}")
    return None


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


def create_app(config: AppConfig) -> FastAPI:
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
        if request.url.path.startswith("/webhook/"):
            return await call_next(request)
        if request.url.path.startswith("/api/dashboard/auth/"):
            return await call_next(request)
        key = request.headers.get("X-API-Key", "")
        if key != api_secret:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
        return await call_next(request)

    # Mount auth API
    from api.auth import init_auth
    from api.auth import router as auth_router

    init_auth(config.database_url)
    app.include_router(auth_router)

    # Mount dashboard API
    from api.dashboard import init_dashboard
    from api.dashboard import router as dashboard_router

    init_dashboard(config)
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
        scheduled_jobs = len(_cron_scheduler.list_jobs()) if _cron_scheduler else 0
        return {
            "status": "ok",
            "agents": agent_count,
            "telegram_bots": len(_telegram_bots),
            "discord_bots": len(_discord_bots),
            "scheduled_jobs": scheduled_jobs,
        }

    return app


def _get_port(config: AppConfig) -> int:
    return config.port


async def _setup_telegram_webhooks(config: AppConfig, manager: AgentManager) -> None:
    """Start Telegram bots and register webhooks for all agents with tokens."""
    from core.crypto import decrypt
    from integrations.telegram.bot import TelegramBot

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
            token = decrypt(record.telegram_token_encrypted)
            bot = TelegramBot(agent, token=token, agent_id=agent_id)
            await bot.start()
            webhook_url = f"{webhook_base}/webhook/{agent_id}"
            await bot.setup_webhook(webhook_url)
            _telegram_bots[agent_id] = bot
        except Exception as e:
            logger.error(f"Failed to setup Telegram bot for agent {agent_id}: {e}")


async def _setup_discord_bots(manager: AgentManager) -> None:
    """Start Discord bots for all agents with Discord tokens."""
    import asyncio

    from core.crypto import decrypt
    from integrations.discord.bot import DiscordBot

    dc_agents = manager.get_discord_agents()
    for agent_id, record in dc_agents.items():
        agent = manager.get(agent_id)
        if not agent:
            logger.warning(f"Agent {agent_id} has Discord token but is not initialized")
            continue
        try:
            token = decrypt(record.discord_token_encrypted)
            bot = DiscordBot(agent, token=token)
            _discord_bots[agent_id] = bot
            asyncio.create_task(bot.start())
            logger.info(f"Started Discord bot for agent {agent_id}")
        except Exception as e:
            logger.error(f"Failed to setup Discord bot for agent {agent_id}: {e}")


async def run_lark(app: FastAPI, config: AppConfig, manager: AgentManager) -> None:
    """Run Lark bots with webhook server for all agents with Lark credentials."""
    import uvicorn

    from core.crypto import decrypt
    from integrations.lark.bot import LarkBot, create_lark_webhook_handler

    lark_agents = manager.get_lark_agents()
    for agent_id, record in lark_agents.items():
        agent = manager.get(agent_id)
        if not agent:
            continue
        try:
            app_id = decrypt(record.lark_app_id_encrypted)
            app_secret = decrypt(record.lark_app_secret_encrypted)
            bot = LarkBot(agent, app_id=app_id, app_secret=app_secret)
            await bot.start()
            handler = create_lark_webhook_handler(bot)

            webhook_path = f"/lark/webhook/{agent_id}"

            @app.post(webhook_path)
            async def lark_webhook(request: Request, _handler=handler):
                body = await request.json()
                return await _handler(body)

            logger.info(f"Lark webhook registered at {webhook_path} for agent {agent_id}")
        except Exception as e:
            logger.error(f"Failed to setup Lark bot for agent {agent_id}: {e}")

    server_config = uvicorn.Config(app, host="0.0.0.0", port=_get_port(config), log_level="info")
    server = uvicorn.Server(server_config)
    await server.serve()


async def run_web_only(app: FastAPI, config: AppConfig) -> None:
    """Run only the web dashboard API (no chat platform)."""
    import uvicorn

    server_config = uvicorn.Config(app, host="0.0.0.0", port=_get_port(config), log_level="info")
    server = uvicorn.Server(server_config)
    await server.serve()


async def run_agent(platform: str = "web") -> None:
    """Main entry point — initialize agent manager and run on configured platform."""
    global _agent_manager, _default_agent, _cron_scheduler

    config = get_config()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logger.info(f"Starting open_intern (platform: {platform})")

    # Create scheduler (lightweight — no jobs loaded yet)
    scheduler = CronScheduler(config.database_url)
    _cron_scheduler = scheduler

    # Initialize agent manager (loads all agents from DB, with scheduler tools)
    manager = AgentManager(config, scheduler=scheduler)
    manager.initialize()
    _agent_manager = manager

    # If no agents in DB, create a default agent
    if not manager.agents:
        logger.info("No agents in DB — creating default agent")
        from core.scheduler import create_scheduler_tools

        extra_tools = create_scheduler_tools(scheduler, "default")
        agent = OpenInternAgent(config, agent_id="default", extra_tools=extra_tools)
        agent.initialize()
        _default_agent = agent
        manager._agents["default"] = agent

    # Now start the scheduler (loads jobs from DB and begins execution)
    scheduler.initialize(manager)
    _cron_scheduler = scheduler

    # Create the FastAPI app
    app = create_app(config)

    # Run on the configured platform
    if platform == "telegram":
        await _setup_telegram_webhooks(config, manager)
        await run_web_only(app, config)
    elif platform == "lark":
        await run_lark(app, config, manager)
    elif platform == "discord":
        await _setup_discord_bots(manager)
        await run_web_only(app, config)
    elif platform == "web":
        logger.info(f"Running in web-only mode (dashboard API on port {config.port})")
        await run_web_only(app, config)
    elif platform == "slack":
        logger.error("Slack integration not yet implemented.")
        sys.exit(1)
    else:
        logger.error(f"Unknown platform: {platform}")
        sys.exit(1)
