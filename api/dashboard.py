"""Dashboard API — REST endpoints for the web UI."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.config import AppConfig, IdentityConfig, LLMConfig
from memory.store import MemoryRecord, MemoryScope, MemoryStore, ThreadMetaRecord
from scripts.seed_skills import list_skills as _list_skills

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# These get set by server.py at startup
_agent = None
_memory_store: MemoryStore | None = None
_config: AppConfig | None = None
_config_path: str = "config/agent.yaml"


def init_dashboard(agent, memory_store: MemoryStore, config: AppConfig, config_path: str):
    global _agent, _memory_store, _config, _config_path
    _agent = agent
    _memory_store = memory_store
    _config = config
    _config_path = config_path
    _load_thread_meta()


# --- Status ---


@router.get("/status")
def get_status():
    if _config is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    stats = _get_memory_stats()
    return {
        "name": _config.identity.name,
        "role": _config.identity.role,
        "platform": _config.active_platform,
        "llm_provider": _config.llm.provider,
        "llm_model": _config.llm.model,
        "memory_stats": stats,
    }


# --- Config ---


@router.get("/config")
def get_config():
    if _config is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    data = _config.model_dump()
    # Redact secrets
    data["llm"]["api_key"] = "***" if data["llm"]["api_key"] else ""
    # Redact top-level API keys
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
def update_identity(body: IdentityUpdate):
    global _config
    if _config is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")
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
def update_llm(body: LLMUpdate):
    global _config
    if _config is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    # Preserve existing api_key
    existing_key = _config.llm.api_key
    _config.llm = LLMConfig(**body.model_dump(), api_key=existing_key)
    _save_config()
    return {"ok": True, "message": "LLM config updated. Restart agent to apply."}


# --- Chat ---

# Thread metadata cache (backed by thread_meta table via SQLAlchemy)
_thread_meta: dict[str, dict] = {}


def _save_thread_meta(thread_id: str, title: str, created_at: str = ""):
    """Save thread metadata to DB and cache."""
    _thread_meta[thread_id] = {"title": title, "created_at": created_at}
    if _memory_store:
        with _memory_store._session() as session:
            existing = session.query(ThreadMetaRecord).filter_by(thread_id=thread_id).first()
            if existing:
                existing.title = title
                existing.created_at = created_at
            else:
                record = ThreadMetaRecord(
                    thread_id=thread_id,
                    title=title,
                    created_at=created_at,
                )
                session.add(record)
            session.commit()


def _load_thread_meta():
    """Load all thread metadata from DB into cache."""
    if _memory_store:
        try:
            with _memory_store._session() as session:
                for row in session.query(ThreadMetaRecord).all():
                    _thread_meta[row.thread_id] = {"title": row.title, "created_at": row.created_at}
        except Exception as e:
            logger.warning(f"Failed to load thread metadata: {e}")


class ChatRequest(BaseModel):
    message: str
    thread_id: str = ""


class ChatResponse(BaseModel):
    response: str
    thread_id: str
    title: str


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest):
    if _agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    from uuid import uuid4

    is_new = not body.thread_id
    thread_id = body.thread_id or str(uuid4())
    response = await _agent.chat(
        body.message,
        context={
            "platform": "web",
            "channel_id": "web-dashboard",
            "user_name": "admin",
            "is_dm": True,
        },
        thread_id=thread_id,
    )

    # Auto-generate title on first message
    if is_new:
        title = _generate_thread_title(body.message, response)
        _save_thread_meta(thread_id, title, datetime.now(timezone.utc).isoformat())
    else:
        title = _thread_meta.get(thread_id, {}).get("title", "")

    return ChatResponse(response=response, thread_id=thread_id, title=title)


def _generate_thread_title(user_message: str, agent_response: str) -> str:
    """Use the LLM to generate a short thread title."""
    if _agent is None or not _agent.is_initialized:
        return user_message[:40]
    try:
        from core.agent import _create_llm

        llm = _create_llm(_agent.config)
        result = llm.invoke(
            "Generate a very short title (max 6 words, no quotes) "
            "for a conversation that starts with:\n"
            f"User: {user_message[:200]}\n"
            f"Reply in the same language as the user message."
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


# --- Threads ---


@router.get("/threads")
def list_threads():
    """List all conversation threads with titles."""
    if _agent is None or not _agent.is_initialized:
        return {"threads": []}
    # Query distinct thread_ids from the checkpoints table
    conn = _agent._checkpoint_conn
    rows = conn.execute("SELECT DISTINCT thread_id FROM checkpoints ORDER BY thread_id").fetchall()
    threads = []
    for row in rows:
        thread_id = row["thread_id"]
        meta = _thread_meta.get(thread_id, {})
        threads.append(
            {
                "thread_id": thread_id,
                "title": meta.get("title", ""),
                "created_at": meta.get("created_at", ""),
            }
        )
    # Sort by created_at descending (threads with metadata first)
    threads.sort(key=lambda t: t["created_at"] or "", reverse=True)
    return {"threads": threads}


@router.get("/threads/{thread_id}")
def get_thread(thread_id: str):
    """Get a thread's metadata."""
    meta = _thread_meta.get(thread_id, {})
    return {"thread_id": thread_id, "title": meta.get("title", "")}


class ThreadTitleUpdate(BaseModel):
    title: str


@router.put("/threads/{thread_id}/title")
def update_thread_title(thread_id: str, body: ThreadTitleUpdate):
    """Update a thread's title."""
    meta = _thread_meta.get(thread_id, {})
    created_at = meta.get("created_at", datetime.now(timezone.utc).isoformat())
    _save_thread_meta(thread_id, body.title, created_at)
    return {"ok": True, "title": body.title}


@router.delete("/threads/{thread_id}")
def delete_thread(thread_id: str):
    """Delete a conversation thread."""
    if _agent is None or not _agent.is_initialized:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    conn = _agent._checkpoint_conn
    result = conn.execute("DELETE FROM checkpoints WHERE thread_id = %s", (thread_id,))
    conn.execute("DELETE FROM checkpoint_blobs WHERE thread_id = %s", (thread_id,))
    conn.execute("DELETE FROM checkpoint_writes WHERE thread_id = %s", (thread_id,))
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Thread not found")
    _thread_meta.pop(thread_id, None)
    if _memory_store:
        with _memory_store._session() as session:
            session.query(ThreadMetaRecord).filter_by(thread_id=thread_id).delete()
            session.commit()
    return {"ok": True}


# --- Memories ---


@router.get("/memories")
def list_memories(scope: str | None = None, limit: int = 50, offset: int = 0):
    if _memory_store is None:
        raise HTTPException(status_code=503, detail="Memory store not initialized")

    with _memory_store._session() as session:
        q = session.query(MemoryRecord)
        if scope:
            q = q.filter(MemoryRecord.scope == scope)
        q = q.order_by(MemoryRecord.created_at.desc())
        total = q.count()
        records = q.offset(offset).limit(limit).all()

        items = []
        for r in records:
            items.append(
                {
                    "id": r.id,
                    "content": r.content,
                    "scope": r.scope,
                    "scope_id": r.scope_id,
                    "source": r.source,
                    "importance": r.importance,
                    "created_at": r.created_at.isoformat() if r.created_at else "",
                }
            )
        return {"items": items, "total": total}


@router.get("/memories/stats")
def memory_stats():
    return _get_memory_stats()


@router.delete("/memories/{memory_id}")
def delete_memory(memory_id: str):
    if _memory_store is None:
        raise HTTPException(status_code=503, detail="Memory store not initialized")
    deleted = _memory_store.forget(memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"ok": True}


# --- Skills ---


@router.get("/skills")
def list_skills():
    """List all agent skills stored in PostgresStore."""
    if _agent is None or not _agent.is_initialized or _agent._postgres_store is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    skills = _list_skills(_agent._postgres_store)
    return {"skills": skills}


_SKILL_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


@router.get("/skills/{skill_name}")
def get_skill(skill_name: str):
    """Get a single skill's details by name."""
    if not _SKILL_NAME_RE.match(skill_name):
        raise HTTPException(status_code=400, detail="Invalid skill name")
    if _agent is None or not _agent.is_initialized or _agent._postgres_store is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    skills = _list_skills(_agent._postgres_store)
    for s in skills:
        if s["name"] == skill_name:
            return s
    raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")


# --- Helpers ---


def _get_memory_stats() -> dict:
    if _memory_store is None:
        return {"shared": 0, "channel": 0, "personal": 0, "total": 0}
    return {
        "shared": _memory_store.count(MemoryScope.SHARED),
        "channel": _memory_store.count(MemoryScope.CHANNEL),
        "personal": _memory_store.count(MemoryScope.PERSONAL),
        "total": _memory_store.count(),
    }


def _save_config():
    """Write current config back to YAML (atomic: write temp file then rename)."""
    if _config is None:
        return
    path = Path(_config_path)
    tmp_path = path.with_suffix(".yaml.tmp")
    data = _config.model_dump()
    content = yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)
    tmp_path.write_text(content)
    tmp_path.replace(path)
    logger.info(f"Config saved to {path}")
