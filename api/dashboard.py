"""Dashboard API — REST endpoints for multi-agent web UI."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from api.auth import get_current_user, get_user_accessible_agents, require_admin
from core.config import AppConfig, IdentityConfig, LLMConfig
from memory.store import MemoryRecord, MemoryScope, MemoryStore, ThreadMetaRecord, TokenUsageRecord
from scripts.seed_skills import list_skills as _list_skills

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# Set by server.py at startup
_config: AppConfig | None = None
_config_path: str = "config/agent.yaml"

# Thread metadata cache: thread_id -> {title, created_at}
_thread_meta: dict[str, dict] = {}


def init_dashboard(config: AppConfig, config_path: str):
    global _config, _config_path
    _config = config
    _config_path = config_path
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
    agent_id: str
    name: str
    role: str = "AI Employee"
    personality: str = "You are a helpful AI employee."
    avatar_url: str = ""
    llm_provider: str = "claude"
    llm_model: str = "claude-sonnet-4-6"
    llm_temperature: float = 0.7
    telegram_token: str = ""
    sandbox_enabled: bool = True


class AgentUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    personality: str | None = None
    avatar_url: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_temperature: float | None = None
    telegram_token: str | None = None
    sandbox_enabled: bool | None = None
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
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


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
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/agents/{agent_id}")
def delete_agent(agent_id: str, admin: dict = Depends(require_admin)):
    mgr = _get_manager()
    try:
        result = mgr.delete_agent(agent_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


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
        "platform": _config.active_platform,
        "agents": len(agent_ids),
        "agent_ids": agent_ids,
    }


# --- Config ---


@router.get("/config")
def get_config(user: dict = Depends(get_current_user)):
    if _config is None:
        raise HTTPException(status_code=503, detail="Not initialized")
    data = _config.model_dump()
    # Redact secrets
    data["llm"]["api_key"] = "***" if data["llm"]["api_key"] else ""
    for key in ("anthropic_api_key", "openai_api_key", "minimax_api_key"):
        if data.get(key):
            data[key] = "***"
    if data.get("api_secret_key"):
        data["api_secret_key"] = "***"
    if data.get("telegram_bot_token"):
        data["telegram_bot_token"] = "***"
    if data.get("discord_bot_token"):
        data["discord_bot_token"] = "***"
    pc = data.get("platform_config", {})
    for platform_name in ("lark", "discord", "slack", "telegram"):
        platform_data = pc.get(platform_name, {})
        for secret_field in ("app_secret", "bot_token", "app_token"):
            if platform_data.get(secret_field):
                platform_data[secret_field] = "***"
    return data


class IdentityUpdate(BaseModel):
    name: str
    role: str
    personality: str
    avatar_url: str = ""


@router.put("/config/identity")
def update_identity(body: IdentityUpdate, admin: dict = Depends(require_admin)):
    global _config
    if _config is None:
        raise HTTPException(status_code=503, detail="Not initialized")
    _config.identity = IdentityConfig(**body.model_dump())
    _save_config()
    return {"ok": True, "message": "Identity updated. Restart agent to apply."}


class LLMUpdate(BaseModel):
    provider: str
    model: str
    temperature: float = 0.7
    max_tokens_per_action: int = 4096
    daily_cost_budget_usd: float = 10.0


@router.put("/config/llm")
def update_llm(body: LLMUpdate, admin: dict = Depends(require_admin)):
    global _config
    if _config is None:
        raise HTTPException(status_code=503, detail="Not initialized")
    existing_key = _config.llm.api_key
    _config.llm = LLMConfig(**body.model_dump(), api_key=existing_key)
    _save_config()
    return {"ok": True, "message": "LLM config updated. Restart agent to apply."}


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

    from uuid import uuid4

    is_new = not body.thread_id
    thread_id = body.thread_id or str(uuid4())
    user_name = user.get("email", "user").split("@")[0]
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
    skills = _list_skills(agent._postgres_store)
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
    skills = _list_skills(agent._postgres_store)
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


# --- Scheduled Jobs ---


def _get_scheduler():
    from server import get_cron_scheduler

    return get_cron_scheduler()


_VALID_SCHEDULE_TYPES = {"cron", "interval", "once"}


class ScheduledJobCreate(BaseModel):
    agent_id: str
    name: str
    schedule_type: str  # "cron" | "interval" | "once"
    schedule_expr: str
    prompt: str
    timezone: str = "UTC"
    channel_id: str = ""
    isolated: bool = False

    @field_validator("schedule_type")
    @classmethod
    def check_schedule_type(cls, v: str) -> str:
        if v not in _VALID_SCHEDULE_TYPES:
            raise ValueError("schedule_type must be 'cron', 'interval', or 'once'")
        return v


class ScheduledJobUpdate(BaseModel):
    name: str | None = None
    schedule_type: str | None = None
    schedule_expr: str | None = None
    timezone: str | None = None
    prompt: str | None = None
    channel_id: str | None = None
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
        result = await scheduler.add_job(
            agent_id=body.agent_id,
            name=body.name,
            schedule_type=body.schedule_type,
            schedule_expr=body.schedule_expr,
            prompt=body.prompt,
            tz=body.timezone,
            channel_id=body.channel_id,
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
    result = await scheduler.update_job(job_id, **updates)
    if result is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return result


@router.delete("/scheduled-jobs/{job_id}")
async def delete_scheduled_job(job_id: str):
    scheduler = _get_scheduler()
    removed = await scheduler.remove_job(job_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"ok": True}


@router.post("/scheduled-jobs/{job_id}/pause")
async def pause_scheduled_job(job_id: str):
    scheduler = _get_scheduler()
    paused = await scheduler.pause_job(job_id)
    if not paused:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"ok": True, "status": "paused"}


@router.post("/scheduled-jobs/{job_id}/resume")
async def resume_scheduled_job(job_id: str):
    scheduler = _get_scheduler()
    resumed = await scheduler.resume_job(job_id)
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


# --- Helpers ---


def _save_config():
    if _config is None:
        return
    path = Path(_config_path)
    tmp_path = path.with_suffix(".yaml.tmp")
    data = _config.model_dump()
    content = yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)
    tmp_path.write_text(content)
    tmp_path.replace(path)
    logger.info(f"Config saved to {path}")
