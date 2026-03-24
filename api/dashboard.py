"""Dashboard API — REST endpoints for multi-agent web UI."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from api.auth import get_current_user, get_user_accessible_agents, require_admin
from core.config import AppConfig
from core.exceptions import AgentNotFoundError, DuplicateAgentError
from memory.store import MemoryRecord, MemoryScope, MemoryStore, ThreadMetaRecord, TokenUsageRecord
from scripts.seed_skills import list_skills as _list_skills

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# Set by server.py at startup
_config: AppConfig | None = None

# Thread metadata cache: thread_id -> {title, created_at}
_thread_meta: dict[str, dict] = {}


def init_dashboard(config: AppConfig):
    global _config
    _config = config
    _load_thread_meta()


def _get_manager():
    from server import get_agent_manager

    return get_agent_manager()


def _get_agent(agent_id: str | None = None):
    from server import get_agent

    return get_agent(agent_id)


def _get_memory_store(agent_id: str | None = None) -> MemoryStore:
    agent = _get_agent(agent_id)
    return agent.memory_store


# --- Agent CRUD ---


class AgentCreate(BaseModel):
    agent_id: str = Field(..., pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(..., min_length=1, max_length=100)
    role: str = "AI Employee"
    personality: str = "You are a helpful AI employee."
    avatar_url: str = ""
    llm_provider: str = "claude"
    llm_model: str = "claude-sonnet-4-6"
    llm_temperature: float = Field(0.7, ge=0.0, le=2.0)
    llm_api_key: str = ""
    max_tokens_per_action: int = Field(4096, ge=1)
    daily_cost_budget_usd: float = Field(10.0, ge=0.0)
    telegram_token: str = ""
    discord_token: str = ""
    lark_app_id: str = ""
    lark_app_secret: str = ""
    slack_bot_token: str = ""
    slack_app_token: str = ""
    platform_type: str = ""
    behavior_config: str = "{}"
    safety_config: str = "{}"
    embedding_model: str = "text-embedding-3-small"
    max_retrieval_results: int = Field(10, ge=1)
    importance_decay_days: int = Field(90, ge=1)
    sandbox_mode: str = "base"  # "none" | "base" | "desktop"


class AgentUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    personality: str | None = None
    avatar_url: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_temperature: float | None = None
    llm_api_key: str | None = None
    max_tokens_per_action: int | None = None
    daily_cost_budget_usd: float | None = None
    telegram_token: str | None = None
    discord_token: str | None = None
    lark_app_id: str | None = None
    lark_app_secret: str | None = None
    slack_bot_token: str | None = None
    slack_app_token: str | None = None
    platform_type: str | None = None
    behavior_config: str | None = None
    safety_config: str | None = None
    embedding_model: str | None = None
    max_retrieval_results: int | None = None
    importance_decay_days: int | None = None
    sandbox_mode: str | None = None  # "none" | "base" | "desktop"
    is_active: bool | None = None


@router.get("/agents")
def list_agents(user: dict = Depends(get_current_user)):
    mgr = _get_manager()
    agents = mgr.list_agents()
    accessible = get_user_accessible_agents(user)
    if accessible is not None:
        agents = [a for a in agents if a["agent_id"] in accessible]
    return {"agents": agents}


@router.post("/agents")
def create_agent(body: AgentCreate, admin: dict = Depends(require_admin)):
    mgr = _get_manager()
    try:
        result = mgr.create_agent(**body.model_dump())
        return result
    except DuplicateAgentError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating agent: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/agents/{agent_id}")
def get_agent_detail(agent_id: str, user: dict = Depends(get_current_user)):
    accessible = get_user_accessible_agents(user)
    if accessible is not None and agent_id not in accessible:
        raise HTTPException(status_code=403, detail="Access denied")
    mgr = _get_manager()
    agents = mgr.list_agents()
    for a in agents:
        if a["agent_id"] == agent_id:
            return a
    raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")


@router.put("/agents/{agent_id}")
def update_agent(agent_id: str, body: AgentUpdate, admin: dict = Depends(require_admin)):
    mgr = _get_manager()
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    try:
        result = mgr.update_agent(agent_id, **updates)
        return result
    except AgentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/agents/{agent_id}")
def delete_agent(agent_id: str, admin: dict = Depends(require_admin)):
    mgr = _get_manager()
    try:
        result = mgr.delete_agent(agent_id)
        return result
    except AgentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/agents/{agent_id}/permanent")
def permanently_delete_agent(agent_id: str, admin: dict = Depends(require_admin)):
    """Permanently delete an agent and all associated data."""
    mgr = _get_manager()
    try:
        result = mgr.permanently_delete_agent(agent_id)
        return result
    except AgentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/agents/{agent_id}/reload")
async def reload_agent(agent_id: str, admin: dict = Depends(require_admin)):
    """Reload an agent's runtime so config changes take effect immediately."""
    mgr = _get_manager()
    agents = mgr.list_agents()
    if not any(a["agent_id"] == agent_id for a in agents):
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    try:
        mgr._reload_agent(agent_id)
    except Exception:
        logger.exception("Failed to reload agent %s", agent_id)
        raise HTTPException(status_code=500, detail="Reload failed due to internal error")
    return {"ok": True, "agent_id": agent_id, "status": "reloaded"}


@router.post("/agents/{agent_id}/sandbox/pause")
async def pause_sandbox(agent_id: str, user: dict = Depends(get_current_user)):
    """Pause the agent's E2B sandbox, preserving its state for later resume."""
    accessible = get_user_accessible_agents(user)
    if accessible is not None and agent_id not in accessible:
        raise HTTPException(status_code=403, detail="Access denied")

    mgr = _get_manager()
    agent = mgr.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    backend = agent._e2b_backend
    if backend is None:
        raise HTTPException(status_code=400, detail="Agent has no E2B sandbox")

    try:
        # Backup to R2 before pausing (best-effort)
        from core.r2_storage import R2Storage

        r2 = R2Storage(_config)
        backup_key = None
        if r2.enabled:
            backup_key = backend.backup_to_r2(r2)

        sandbox_id = backend.pause()
        if sandbox_id:
            mgr._update_sandbox_id(agent_id, sandbox_id)
            return {
                "ok": True,
                "agent_id": agent_id,
                "sandbox_id": sandbox_id,
                "status": "paused",
                "backup_key": backup_key,
            }
        raise HTTPException(status_code=500, detail="Sandbox pause returned no ID")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to pause sandbox for {agent_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to pause sandbox")


@router.post("/agents/{agent_id}/sandbox/resume")
async def resume_sandbox(agent_id: str, user: dict = Depends(get_current_user)):
    """Resume a previously paused E2B sandbox."""
    accessible = get_user_accessible_agents(user)
    if accessible is not None and agent_id not in accessible:
        raise HTTPException(status_code=403, detail="Access denied")

    mgr = _get_manager()
    agent = mgr.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    backend = agent._e2b_backend
    if backend is None:
        raise HTTPException(status_code=400, detail="Agent has no E2B sandbox")

    try:
        backend.connect()
        new_id = backend.sandbox_id
        if not new_id:
            raise HTTPException(status_code=500, detail="Sandbox resume did not return a valid ID")
        mgr._update_sandbox_id(agent_id, new_id)
        return {"ok": True, "agent_id": agent_id, "sandbox_id": new_id, "status": "running"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resume sandbox for {agent_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to resume sandbox")


@router.post("/agents/{agent_id}/sandbox/backup")
async def backup_sandbox(agent_id: str, user: dict = Depends(get_current_user)):
    """Manually trigger a sandbox backup to R2."""
    accessible = get_user_accessible_agents(user)
    if accessible is not None and agent_id not in accessible:
        raise HTTPException(status_code=403, detail="Access denied")

    mgr = _get_manager()
    agent = mgr.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    backend = agent._e2b_backend
    if backend is None:
        raise HTTPException(status_code=400, detail="Agent has no E2B sandbox")

    from core.r2_storage import R2Storage

    r2 = R2Storage(_config)
    if not r2.enabled:
        raise HTTPException(status_code=400, detail="R2 backup not configured")

    try:
        key = backend.backup_to_r2(r2)
        if not key:
            raise HTTPException(status_code=500, detail="Backup failed")
        return {"ok": True, "agent_id": agent_id, "key": key}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Backup failed for {agent_id}: {e}")
        raise HTTPException(status_code=500, detail="Backup failed")


@router.get("/agents/{agent_id}/sandbox/backups")
async def list_sandbox_backups(agent_id: str, user: dict = Depends(get_current_user)):
    """List available sandbox backups from R2."""
    accessible = get_user_accessible_agents(user)
    if accessible is not None and agent_id not in accessible:
        raise HTTPException(status_code=403, detail="Access denied")

    from core.r2_storage import R2Storage

    r2 = R2Storage(_config)
    if not r2.enabled:
        return {"backups": []}

    backups = r2.list_backups(agent_id)
    return {"backups": backups}


@router.post("/agents/{agent_id}/sandbox/restore")
async def restore_sandbox(agent_id: str, user: dict = Depends(get_current_user)):
    """Restore latest R2 backup into the running sandbox."""
    accessible = get_user_accessible_agents(user)
    if accessible is not None and agent_id not in accessible:
        raise HTTPException(status_code=403, detail="Access denied")

    mgr = _get_manager()
    agent = mgr.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    backend = agent._e2b_backend
    if backend is None:
        raise HTTPException(status_code=400, detail="Agent has no E2B sandbox")

    from core.r2_storage import R2Storage

    r2 = R2Storage(_config)
    if not r2.enabled:
        raise HTTPException(status_code=400, detail="R2 backup not configured")

    try:
        restored = backend.restore_from_r2(r2)
        if not restored:
            raise HTTPException(status_code=404, detail="No backup found to restore")
        return {"ok": True, "agent_id": agent_id, "status": "restored"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Restore failed for {agent_id}: {e}")
        raise HTTPException(status_code=500, detail="Restore failed")


@router.post("/agents/{agent_id}/desktop-stream")
async def start_desktop_stream(agent_id: str, user: dict = Depends(get_current_user)):
    """Start desktop sandbox streaming and return the noVNC URL."""
    accessible = get_user_accessible_agents(user)
    if accessible is not None and agent_id not in accessible:
        raise HTTPException(status_code=403, detail="Access denied")

    mgr = _get_manager()
    agent = mgr.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    backend = agent._e2b_backend
    if backend is None:
        raise HTTPException(status_code=400, detail="Agent has no E2B sandbox configured")

    from core.e2b_desktop_backend import E2BDesktopBackend

    if not isinstance(backend, E2BDesktopBackend):
        raise HTTPException(
            status_code=400,
            detail="Agent sandbox mode is not 'desktop'. Change sandbox_mode to 'desktop' first.",
        )

    try:
        url = backend.start_stream()
        return {"stream_url": url, "agent_id": agent_id}
    except Exception as e:
        logger.error(f"Failed to start desktop stream for {agent_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start stream: {e}")


@router.delete("/agents/{agent_id}/desktop-stream")
async def stop_desktop_stream(agent_id: str, user: dict = Depends(get_current_user)):
    """Stop desktop sandbox streaming."""
    accessible = get_user_accessible_agents(user)
    if accessible is not None and agent_id not in accessible:
        raise HTTPException(status_code=403, detail="Access denied")

    mgr = _get_manager()
    agent = mgr.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    backend = agent._e2b_backend
    from core.e2b_desktop_backend import E2BDesktopBackend

    if isinstance(backend, E2BDesktopBackend):
        backend.stop_stream()
    return {"ok": True, "agent_id": agent_id}


@router.get("/agents/{agent_id}/desktop-stream")
async def get_desktop_stream(agent_id: str, user: dict = Depends(get_current_user)):
    """Get current desktop stream URL if active."""
    accessible = get_user_accessible_agents(user)
    if accessible is not None and agent_id not in accessible:
        raise HTTPException(status_code=403, detail="Access denied")

    mgr = _get_manager()
    agent = mgr.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    backend = agent._e2b_backend
    from core.e2b_desktop_backend import E2BDesktopBackend

    if isinstance(backend, E2BDesktopBackend) and backend.stream_url:
        return {"stream_url": backend.stream_url, "agent_id": agent_id, "active": True}
    return {"stream_url": None, "agent_id": agent_id, "active": False}


class TelegramTestRequest(BaseModel):
    chat_id: str = Field(..., pattern=r"^-?\d+$")
    message: str = Field(
        default="Hello from open_intern! Your Telegram connection is working.",
        max_length=4096,
    )


@router.post("/agents/{agent_id}/test-telegram")
async def test_telegram(
    agent_id: str,
    body: TelegramTestRequest,
    admin: dict = Depends(require_admin),
):
    """Send a test message via Telegram bot to verify the connection."""
    mgr = _get_manager()
    from memory.store import AgentRecord

    with mgr._session_factory() as session:
        record = (
            session.query(AgentRecord)
            .filter_by(
                agent_id=agent_id,
            )
            .first()
        )
        if not record:
            raise HTTPException(
                status_code=404,
                detail=f"Agent '{agent_id}' not found",
            )
        if not record.telegram_token_encrypted:
            raise HTTPException(
                status_code=400,
                detail="No Telegram token configured for this agent",
            )

        from core.crypto import decrypt

        token = decrypt(record.telegram_token_encrypted)

    try:
        import httpx

        tg_api = f"https://api.telegram.org/bot{token}"
        async with httpx.AsyncClient() as client:
            # First verify the token by calling getMe
            me_resp = await client.get(f"{tg_api}/getMe")
            me_data = me_resp.json()
            if not me_data.get("ok"):
                desc = me_data.get("description", "unknown error")
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid Telegram token: {desc}",
                )

            bot_username = me_data["result"].get("username", "unknown")

            # Send test message
            send_resp = await client.post(
                f"{tg_api}/sendMessage",
                json={"chat_id": body.chat_id, "text": body.message},
            )
            send_data = send_resp.json()
            if not send_data.get("ok"):
                desc = send_data.get("description", "unknown error")
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to send: {desc}",
                )

        return {
            "ok": True,
            "bot_username": bot_username,
            "chat_id": body.chat_id,
            "message": "Test message sent successfully.",
        }
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Telegram API request failed: {e}",
        )


# --- Status ---


@router.get("/status")
def get_status(user: dict = Depends(get_current_user)):
    if _config is None:
        raise HTTPException(status_code=503, detail="Not initialized")
    mgr = _get_manager()
    accessible = get_user_accessible_agents(user)
    agent_ids = list(mgr.agents.keys())
    if accessible is not None:
        agent_ids = [a for a in agent_ids if a in accessible]
    return {
        "agents": len(agent_ids),
        "agent_ids": agent_ids,
    }


# --- System Settings ---


class SettingUpsert(BaseModel):
    value: str
    is_secret: bool = False
    description: str = ""


@router.get("/settings")
def list_settings(user: dict = Depends(get_current_user)):
    mgr = _get_manager()
    return {"settings": mgr.get_system_settings()}


@router.put("/settings/{key}")
def upsert_setting(key: str, body: SettingUpsert, admin: dict = Depends(require_admin)):
    mgr = _get_manager()
    result = mgr.upsert_system_setting(
        key=key,
        value=body.value,
        is_secret=body.is_secret,
        description=body.description,
    )
    return result


@router.delete("/settings/{key}")
def delete_setting(key: str, admin: dict = Depends(require_admin)):
    mgr = _get_manager()
    deleted = mgr.delete_system_setting(key)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")
    return {"ok": True}


# --- Chat (per-agent) ---


def _save_thread_meta(
    thread_id: str,
    title: str,
    created_at: str = "",
    agent_id: str = "default",
    user_id: str = "",
):
    _thread_meta[thread_id] = {
        "title": title,
        "created_at": created_at,
        "agent_id": agent_id,
        "user_id": user_id,
    }
    store = _get_memory_store(agent_id)
    with store._session() as session:
        existing = session.query(ThreadMetaRecord).filter_by(thread_id=thread_id).first()
        if existing:
            existing.title = title
            existing.created_at = created_at
        else:
            record = ThreadMetaRecord(
                thread_id=thread_id,
                agent_id=agent_id,
                title=title,
                created_at=created_at,
                user_id=user_id or None,
            )
            session.add(record)
        session.commit()


def _load_thread_meta():
    """Load thread metadata from DB. Gracefully handles missing columns."""
    if _config is None:
        return
    try:
        import psycopg
        from psycopg.rows import dict_row

        with psycopg.connect(_config.database_url, autocommit=True, row_factory=dict_row) as conn:
            # Check which columns exist
            cols = conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name='thread_meta'"
            ).fetchall()
            col_names = {c["column_name"] for c in cols}
            has_agent_id = "agent_id" in col_names
            has_user_id = "user_id" in col_names

            select_cols = "thread_id, title, created_at"
            if has_agent_id:
                select_cols += ", agent_id"
            if has_user_id:
                select_cols += ", user_id"

            rows = conn.execute(f"SELECT {select_cols} FROM thread_meta").fetchall()

            for row in rows:
                _thread_meta[row["thread_id"]] = {
                    "title": row["title"],
                    "created_at": row["created_at"],
                    "agent_id": row.get("agent_id", "default"),
                    "user_id": row.get("user_id", ""),
                }
            logger.info(f"Loaded {len(rows)} thread metadata entries")
    except Exception as e:
        logger.warning(f"Failed to load thread metadata: {e}")


class ChatRequest(BaseModel):
    message: str
    thread_id: str = ""
    agent_id: str = ""


class ChatResponse(BaseModel):
    response: str
    thread_id: str
    title: str
    agent_id: str
    token_usage: dict[str, int] = {}


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, user: dict = Depends(get_current_user)):
    agent_id = body.agent_id or "default"
    # Check user has access to this agent
    accessible = get_user_accessible_agents(user)
    if accessible is not None and agent_id not in accessible:
        raise HTTPException(status_code=403, detail="Access denied to this agent")
    try:
        agent = _get_agent(agent_id)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not available")

    # Check API key is configured before attempting LLM call
    if not agent.config.llm.api_key:
        raise HTTPException(
            status_code=422,
            detail="NO_API_KEY: This agent has no LLM API key configured. "
            "Set one in the agent's edit page, or configure a system default "
            "in Settings.",
        )

    from uuid import uuid4

    is_new = not body.thread_id
    thread_id = body.thread_id or str(uuid4())
    user_name = user.get("email", "user").split("@")[0]
    try:
        response, token_usage = await agent.chat(
            body.message,
            context={
                "platform": "web",
                "channel_id": "web-dashboard",
                "user_name": user_name,
                "user_id": user.get("user_id", ""),
                "is_dm": True,
            },
            thread_id=thread_id,
        )
    except Exception as e:
        logger.error("Chat failed for agent %s: %s", agent_id, e)
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred while processing your request.",
        )

    user_id = user.get("user_id", "")

    # Store token usage
    if token_usage.get("total_tokens", 0) > 0:
        _store_token_usage(agent_id, thread_id, user_id, token_usage)

    if is_new:
        title = _generate_thread_title(agent, body.message)
        _save_thread_meta(
            thread_id, title, datetime.now(timezone.utc).isoformat(), agent_id, user_id
        )
    else:
        title = _thread_meta.get(thread_id, {}).get("title", "")

    return ChatResponse(
        response=response,
        thread_id=thread_id,
        title=title,
        agent_id=agent_id,
        token_usage=token_usage,
    )


@router.post("/chat/stream")
async def chat_stream(body: ChatRequest, user: dict = Depends(get_current_user)):
    """SSE streaming chat endpoint. Sends token-by-token events."""
    agent_id = body.agent_id or "default"
    accessible = get_user_accessible_agents(user)
    if accessible is not None and agent_id not in accessible:
        raise HTTPException(status_code=403, detail="Access denied to this agent")
    try:
        agent = _get_agent(agent_id)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not available")

    if not agent.config.llm.api_key:
        raise HTTPException(
            status_code=422,
            detail="NO_API_KEY: This agent has no LLM API key configured. "
            "Set one in the agent's edit page, or configure a system default "
            "in Settings.",
        )

    from uuid import uuid4

    is_new = not body.thread_id
    thread_id = body.thread_id or str(uuid4())
    user_name = user.get("email", "user").split("@")[0]

    async def event_generator():
        token_usage = {}
        try:
            async for chunk in agent.chat_stream(
                body.message,
                context={
                    "platform": "web",
                    "channel_id": "web-dashboard",
                    "user_name": user_name,
                    "user_id": user.get("user_id", ""),
                    "is_dm": True,
                },
                thread_id=thread_id,
            ):
                if chunk["type"] == "token":
                    yield f"data: {json.dumps(chunk)}\n\n"
                elif chunk["type"] == "status":
                    yield f"data: {json.dumps(chunk)}\n\n"
                elif chunk["type"] == "done":
                    token_usage = chunk.get("token_usage", {})
        except Exception as e:
            logger.error("Streaming chat failed for agent %s: %s", agent_id, e)
            err_data = {"type": "error", "content": "An error occurred."}
            yield f"data: {json.dumps(err_data)}\n\n"
            return

        user_id = user.get("user_id", "")

        # Store token usage
        if token_usage.get("total_tokens", 0) > 0:
            _store_token_usage(agent_id, thread_id, user_id, token_usage)

        title = ""
        if is_new:
            title = _generate_thread_title(agent, body.message)
            _save_thread_meta(
                thread_id,
                title,
                datetime.now(timezone.utc).isoformat(),
                agent_id,
                user_id,
            )
        else:
            title = _thread_meta.get(thread_id, {}).get("title", "")

        # Send final done event with metadata
        done_data = {
            "type": "done",
            "thread_id": thread_id,
            "title": title,
            "agent_id": agent_id,
            "token_usage": token_usage,
        }
        yield f"data: {json.dumps(done_data)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _generate_thread_title(agent, user_message: str) -> str:
    if not agent.is_initialized:
        return user_message[:40]
    try:
        from core.agent import _create_llm

        llm = _create_llm(agent.config)
        result = llm.invoke(
            "Generate a very short title (max 6 words, no quotes) "
            "for a conversation that starts with:\n"
            f"User: {user_message[:200]}\n"
            "Reply in the same language as the user message."
        )
        content = result.content
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    return block["text"].strip()[:50]
        return str(content).strip()[:50]
    except Exception as e:
        logger.warning(f"Failed to generate thread title: {e}")
        return user_message[:40]


# --- Threads (per-agent) ---


@router.get("/threads")
def list_threads(agent_id: str = "", user: dict = Depends(get_current_user)):
    """List conversation threads, filtered by user access and optionally by agent_id."""
    accessible = get_user_accessible_agents(user)
    user_id = user.get("user_id", "")
    is_admin = user.get("role") == "admin"

    threads = []
    for tid, meta in _thread_meta.items():
        if agent_id and meta.get("agent_id", "default") != agent_id:
            continue
        # Users only see their own threads
        if not is_admin and meta.get("user_id") and meta["user_id"] != user_id:
            continue
        # Users only see threads for agents they have access to
        if accessible is not None and meta.get("agent_id", "default") not in accessible:
            continue
        threads.append(
            {
                "thread_id": tid,
                "title": meta.get("title", ""),
                "created_at": meta.get("created_at", ""),
                "agent_id": meta.get("agent_id", "default"),
            }
        )
    threads.sort(key=lambda t: t["created_at"] or "", reverse=True)
    return {"threads": threads}


def _check_thread_access(thread_id: str, user: dict) -> dict:
    """Check if user can access this thread. Returns thread meta or raises 403."""
    meta = _thread_meta.get(thread_id, {})
    is_admin = user.get("role") == "admin"
    user_id = user.get("user_id", "")
    if not is_admin and meta.get("user_id") and meta["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    accessible = get_user_accessible_agents(user)
    if accessible is not None and meta.get("agent_id", "default") not in accessible:
        raise HTTPException(status_code=403, detail="Access denied")
    return meta


@router.get("/threads/{thread_id}")
def get_thread(thread_id: str, user: dict = Depends(get_current_user)):
    meta = _check_thread_access(thread_id, user)
    return {
        "thread_id": thread_id,
        "title": meta.get("title", ""),
        "agent_id": meta.get("agent_id", "default"),
    }


class ThreadTitleUpdate(BaseModel):
    title: str


@router.put("/threads/{thread_id}/title")
def update_thread_title(
    thread_id: str, body: ThreadTitleUpdate, user: dict = Depends(get_current_user)
):
    _check_thread_access(thread_id, user)
    meta = _thread_meta.get(thread_id, {})
    agent_id = meta.get("agent_id", "default")
    created_at = meta.get("created_at", datetime.now(timezone.utc).isoformat())
    _save_thread_meta(thread_id, body.title, created_at, agent_id)
    return {"ok": True, "title": body.title}


@router.delete("/threads/{thread_id}")
def delete_thread(thread_id: str, user: dict = Depends(get_current_user)):
    _check_thread_access(thread_id, user)
    meta = _thread_meta.get(thread_id, {})
    agent_id = meta.get("agent_id", "default")
    try:
        agent = _get_agent(agent_id)
    except Exception:
        raise HTTPException(status_code=503, detail="Agent not available")
    if not agent.is_initialized:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    conn = agent._checkpoint_conn
    result = conn.execute("DELETE FROM checkpoints WHERE thread_id = %s", (thread_id,))
    conn.execute("DELETE FROM checkpoint_blobs WHERE thread_id = %s", (thread_id,))
    conn.execute("DELETE FROM checkpoint_writes WHERE thread_id = %s", (thread_id,))
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Thread not found")
    _thread_meta.pop(thread_id, None)
    store = _get_memory_store(agent_id)
    with store._session() as session:
        session.query(ThreadMetaRecord).filter_by(thread_id=thread_id).delete()
        session.commit()
    return {"ok": True}


# --- Memories (per-agent) ---


@router.get("/memories")
def list_memories(
    agent_id: str = "",
    scope: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user: dict = Depends(get_current_user),
):
    aid = agent_id or "default"
    store = _get_memory_store(aid)
    with store._session() as session:
        q = session.query(MemoryRecord).filter(MemoryRecord.agent_id == aid)
        if scope:
            q = q.filter(MemoryRecord.scope == scope)
        q = q.order_by(MemoryRecord.created_at.desc())
        total = q.count()
        records = q.offset(offset).limit(limit).all()
        items = [
            {
                "id": r.id,
                "content": r.content,
                "scope": r.scope,
                "scope_id": r.scope_id,
                "source": r.source,
                "importance": r.importance,
                "created_at": r.created_at.isoformat() if r.created_at else "",
                "agent_id": r.agent_id,
            }
            for r in records
        ]
        return {"items": items, "total": total}


@router.get("/memories/stats")
def memory_stats(agent_id: str = "", user: dict = Depends(get_current_user)):
    aid = agent_id or "default"
    store = _get_memory_store(aid)
    return {
        "shared": store.count(MemoryScope.SHARED),
        "channel": store.count(MemoryScope.CHANNEL),
        "personal": store.count(MemoryScope.PERSONAL),
        "total": store.count(),
        "agent_id": aid,
    }


@router.delete("/memories/{memory_id}")
def delete_memory(memory_id: str, agent_id: str = "", user: dict = Depends(get_current_user)):
    aid = agent_id or "default"
    store = _get_memory_store(aid)
    deleted = store.forget(memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"ok": True}


# --- Skills ---


@router.get("/skills")
def list_skills(agent_id: str = "", user: dict = Depends(get_current_user)):
    try:
        agent = _get_agent(agent_id or None)
    except Exception:
        raise HTTPException(status_code=503, detail="Agent not available")
    if not agent.is_initialized or agent._postgres_store is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    skills = _list_skills(agent._postgres_store, agent_id=agent.agent_id)
    return {"skills": skills}


_SKILL_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


@router.get("/skills/{skill_name}")
def get_skill(skill_name: str, agent_id: str = "", user: dict = Depends(get_current_user)):
    if not _SKILL_NAME_RE.match(skill_name):
        raise HTTPException(status_code=400, detail="Invalid skill name")
    try:
        agent = _get_agent(agent_id or None)
    except Exception:
        raise HTTPException(status_code=503, detail="Agent not available")
    if not agent.is_initialized or agent._postgres_store is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    skills = _list_skills(agent._postgres_store, agent_id=agent.agent_id)
    for s in skills:
        if s["name"] == skill_name:
            return s
    raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")


# --- Token Usage ---


def _store_token_usage(agent_id: str, thread_id: str, user_id: str, usage: dict[str, int]):
    """Store a token usage record."""
    from uuid import uuid4 as _uuid4

    store = _get_memory_store(agent_id)
    with store._session() as session:
        record = TokenUsageRecord(
            id=str(_uuid4()),
            agent_id=agent_id,
            thread_id=thread_id,
            user_id=user_id,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            created_at=datetime.now(timezone.utc),
        )
        session.add(record)
        session.commit()


@router.get("/token-usage/thread/{thread_id}")
def get_thread_token_usage(thread_id: str, user: dict = Depends(get_current_user)):
    """Get total token usage for a specific thread."""
    _check_thread_access(thread_id, user)
    if _config is None:
        raise HTTPException(status_code=503, detail="Not initialized")
    from sqlalchemy import func

    store = _get_memory_store()
    with store._session() as session:
        row = (
            session.query(
                func.coalesce(func.sum(TokenUsageRecord.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(TokenUsageRecord.output_tokens), 0).label("output_tokens"),
                func.coalesce(func.sum(TokenUsageRecord.total_tokens), 0).label("total_tokens"),
                func.count(TokenUsageRecord.id).label("request_count"),
            )
            .filter(TokenUsageRecord.thread_id == thread_id)
            .first()
        )
        return {
            "thread_id": thread_id,
            "input_tokens": row.input_tokens if row else 0,
            "output_tokens": row.output_tokens if row else 0,
            "total_tokens": row.total_tokens if row else 0,
            "request_count": row.request_count if row else 0,
        }


@router.get("/token-usage/agent/{agent_id}")
def get_agent_token_usage(agent_id: str, user: dict = Depends(get_current_user)):
    """Get total token usage for a specific agent."""
    accessible = get_user_accessible_agents(user)
    if accessible is not None and agent_id not in accessible:
        raise HTTPException(status_code=403, detail="Access denied")
    if _config is None:
        raise HTTPException(status_code=503, detail="Not initialized")
    from sqlalchemy import func

    store = _get_memory_store(agent_id)
    with store._session() as session:
        row = (
            session.query(
                func.coalesce(func.sum(TokenUsageRecord.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(TokenUsageRecord.output_tokens), 0).label("output_tokens"),
                func.coalesce(func.sum(TokenUsageRecord.total_tokens), 0).label("total_tokens"),
                func.count(TokenUsageRecord.id).label("request_count"),
            )
            .filter(TokenUsageRecord.agent_id == agent_id)
            .first()
        )
        return {
            "agent_id": agent_id,
            "input_tokens": row.input_tokens if row else 0,
            "output_tokens": row.output_tokens if row else 0,
            "total_tokens": row.total_tokens if row else 0,
            "request_count": row.request_count if row else 0,
        }


@router.get("/token-usage/summary")
def get_token_usage_summary(user: dict = Depends(get_current_user)):
    """Get token usage summary for all agents, with per-agent breakdown."""
    if _config is None:
        raise HTTPException(status_code=503, detail="Not initialized")
    from sqlalchemy import func

    accessible = get_user_accessible_agents(user)
    store = _get_memory_store()
    with store._session() as session:
        q = session.query(
            TokenUsageRecord.agent_id,
            func.coalesce(func.sum(TokenUsageRecord.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(TokenUsageRecord.output_tokens), 0).label("output_tokens"),
            func.coalesce(func.sum(TokenUsageRecord.total_tokens), 0).label("total_tokens"),
            func.count(TokenUsageRecord.id).label("request_count"),
        ).group_by(TokenUsageRecord.agent_id)

        if accessible is not None:
            q = q.filter(TokenUsageRecord.agent_id.in_(accessible))

        agents = []
        grand_input = 0
        grand_output = 0
        grand_total = 0
        grand_requests = 0
        for row in q.all():
            agents.append(
                {
                    "agent_id": row.agent_id,
                    "input_tokens": row.input_tokens,
                    "output_tokens": row.output_tokens,
                    "total_tokens": row.total_tokens,
                    "request_count": row.request_count,
                }
            )
            grand_input += row.input_tokens
            grand_output += row.output_tokens
            grand_total += row.total_tokens
            grand_requests += row.request_count

        return {
            "agents": agents,
            "total": {
                "input_tokens": grand_input,
                "output_tokens": grand_output,
                "total_tokens": grand_total,
                "request_count": grand_requests,
            },
        }


@router.get("/token-usage/timeseries")
def get_token_usage_timeseries(
    start: str | None = None,
    end: str | None = None,
    agent_id: str | None = None,
    user: dict = Depends(get_current_user),
):
    """Get daily token usage timeseries, optionally filtered by agent and date range."""
    if _config is None:
        raise HTTPException(status_code=503, detail="Not initialized")
    from sqlalchemy import Date, cast, func

    accessible = get_user_accessible_agents(user)
    if agent_id and accessible is not None and agent_id not in accessible:
        raise HTTPException(status_code=403, detail="Access denied")

    store = _get_memory_store(agent_id or "default")
    with store._session() as session:
        day_col = cast(TokenUsageRecord.created_at, Date).label("day")
        q = (
            session.query(
                day_col,
                TokenUsageRecord.agent_id,
                func.coalesce(func.sum(TokenUsageRecord.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(TokenUsageRecord.output_tokens), 0).label("output_tokens"),
                func.coalesce(func.sum(TokenUsageRecord.total_tokens), 0).label("total_tokens"),
                func.count(TokenUsageRecord.id).label("request_count"),
            )
            .group_by(day_col, TokenUsageRecord.agent_id)
            .order_by(day_col)
        )

        if agent_id:
            q = q.filter(TokenUsageRecord.agent_id == agent_id)
        elif accessible is not None:
            q = q.filter(TokenUsageRecord.agent_id.in_(accessible))

        if start:
            try:
                start_dt = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
                q = q.filter(TokenUsageRecord.created_at >= start_dt)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid start date")
        if end:
            try:
                end_dt = datetime.fromisoformat(end).replace(tzinfo=timezone.utc)
                q = q.filter(TokenUsageRecord.created_at <= end_dt)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid end date")

        points = []
        for row in q.all():
            points.append(
                {
                    "date": row.day.isoformat() if row.day else "",
                    "agent_id": row.agent_id,
                    "input_tokens": row.input_tokens,
                    "output_tokens": row.output_tokens,
                    "total_tokens": row.total_tokens,
                    "request_count": row.request_count,
                }
            )

        return {"points": points}


# --- Scheduled Jobs ---


def _get_scheduler():
    from server import get_cron_scheduler

    return get_cron_scheduler()


_VALID_SCHEDULE_TYPES = {"cron", "interval", "once"}
_VALID_DELIVERY_PLATFORMS = {"", "lark", "telegram", "discord"}


class ScheduledJobCreate(BaseModel):
    agent_id: str
    name: str
    schedule_type: str  # "cron" | "interval" | "once"
    schedule_expr: str
    prompt: str
    timezone: str = "UTC"
    channel_id: str = ""
    delivery_platform: str = ""
    delivery_chat_id: str = ""
    isolated: bool = False

    @field_validator("schedule_type")
    @classmethod
    def check_schedule_type(cls, v: str) -> str:
        if v not in _VALID_SCHEDULE_TYPES:
            raise ValueError("schedule_type must be 'cron', 'interval', or 'once'")
        return v

    @field_validator("delivery_platform")
    @classmethod
    def check_delivery_platform(cls, v: str) -> str:
        if v not in _VALID_DELIVERY_PLATFORMS:
            raise ValueError("delivery_platform must be '', 'telegram', or 'discord'")
        return v


class ScheduledJobUpdate(BaseModel):
    name: str | None = None
    schedule_type: str | None = None
    schedule_expr: str | None = None
    timezone: str | None = None
    prompt: str | None = None
    channel_id: str | None = None
    delivery_platform: str | None = None
    delivery_chat_id: str | None = None
    isolated: bool | None = None
    enabled: bool | None = None

    @field_validator("schedule_type")
    @classmethod
    def check_schedule_type(cls, v: str | None) -> str | None:
        if v is not None and v not in _VALID_SCHEDULE_TYPES:
            raise ValueError("schedule_type must be 'cron', 'interval', or 'once'")
        return v


@router.get("/scheduled-jobs")
def list_scheduled_jobs(agent_id: str = ""):
    scheduler = _get_scheduler()
    jobs = scheduler.list_jobs(agent_id=agent_id or None)
    return {"jobs": jobs}


@router.post("/scheduled-jobs")
async def create_scheduled_job(body: ScheduledJobCreate):
    scheduler = _get_scheduler()
    try:
        result = scheduler.add_job(
            agent_id=body.agent_id,
            name=body.name,
            schedule_type=body.schedule_type,
            schedule_expr=body.schedule_expr,
            prompt=body.prompt,
            tz=body.timezone,
            channel_id=body.channel_id,
            delivery_platform=body.delivery_platform,
            delivery_chat_id=body.delivery_chat_id,
            isolated=body.isolated,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/scheduled-jobs/{job_id}")
def get_scheduled_job(job_id: str):
    scheduler = _get_scheduler()
    job = scheduler.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.put("/scheduled-jobs/{job_id}")
async def update_scheduled_job(job_id: str, body: ScheduledJobUpdate):
    scheduler = _get_scheduler()
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = scheduler.update_job(job_id, **updates)
    if result is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return result


@router.delete("/scheduled-jobs/{job_id}")
async def delete_scheduled_job(job_id: str):
    scheduler = _get_scheduler()
    removed = scheduler.remove_job(job_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"ok": True}


@router.post("/scheduled-jobs/{job_id}/pause")
async def pause_scheduled_job(job_id: str):
    scheduler = _get_scheduler()
    paused = scheduler.pause_job(job_id)
    if not paused:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"ok": True, "status": "paused"}


@router.post("/scheduled-jobs/{job_id}/resume")
async def resume_scheduled_job(job_id: str):
    scheduler = _get_scheduler()
    resumed = scheduler.resume_job(job_id)
    if not resumed:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"ok": True, "status": "resumed"}


@router.post("/scheduled-jobs/{job_id}/trigger")
async def trigger_scheduled_job(job_id: str):
    scheduler = _get_scheduler()
    triggered = await scheduler.trigger_job(job_id)
    if not triggered:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"ok": True, "status": "triggered"}


# --- Cost Guard ---


@router.get("/cost-guard/{agent_id}")
def get_cost_guard_status(agent_id: str, user: dict = Depends(get_current_user)):
    """Get cost guard status for an agent (daily spend, budget, rate limits)."""
    accessible = get_user_accessible_agents(user)
    if accessible is not None and agent_id not in accessible:
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        agent = _get_agent(agent_id)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not available")
    return agent.cost_guard.get_status()


# --- Heartbeat ---


def _get_heartbeat_runner():
    from server import _get_app

    app = _get_app()
    runner = getattr(app.state, "heartbeat_runner", None)
    if runner is None:
        raise HTTPException(status_code=503, detail="Heartbeat runner not initialized")
    return runner


@router.get("/heartbeat/status")
def get_heartbeat_status(user: dict = Depends(get_current_user)):
    """Get heartbeat status for all registered agents."""
    runner = _get_heartbeat_runner()
    return {"agents": runner.get_status()}


@router.post("/heartbeat/{agent_id}/trigger")
async def trigger_heartbeat(agent_id: str, user: dict = Depends(get_current_user)):
    """Manually trigger a heartbeat for an agent."""
    accessible = get_user_accessible_agents(user)
    if accessible is not None and agent_id not in accessible:
        raise HTTPException(status_code=403, detail="Access denied")
    runner = _get_heartbeat_runner()
    result = await runner.trigger_heartbeat(agent_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result
