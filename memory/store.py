"""Memory storage — persistent organizational memory with 3-layer isolation."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

import sqlalchemy
from pydantic import BaseModel, Field
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

logger = logging.getLogger(__name__)


class MemoryScope(str, Enum):
    SHARED = "shared"  # org-wide, visible to all
    CHANNEL = "channel"  # visible only in a specific channel context
    PERSONAL = "personal"  # visible only in DMs with a specific user


class MemoryEntry(BaseModel):
    """A single memory record."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    content: str
    scope: MemoryScope
    scope_id: str = ""  # channel_id or user_id, empty for shared
    source: str = ""  # where this memory came from (slack msg, notion doc, etc.)
    importance: float = 0.5
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class Base(DeclarativeBase):
    pass


class SystemSettingRecord(Base):
    """Admin-managed key-value store for system-wide defaults. Secrets encrypted with Fernet."""

    __tablename__ = "system_settings"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=False, default="")
    is_secret = Column(Boolean, nullable=False, default=False)
    description = Column(Text, nullable=False, default="")
    updated_at = Column(DateTime(timezone=True), nullable=False)


class AgentRecord(Base):
    """Registered agent with its own identity, LLM config, and platform tokens."""

    __tablename__ = "agents"

    agent_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    role = Column(String, nullable=False, default="AI Employee")
    personality = Column(Text, nullable=False, default="You are a helpful AI employee.")
    avatar_url = Column(String, nullable=False, default="")

    # LLM config
    llm_provider = Column(String, nullable=False, default="claude")
    llm_model = Column(String, nullable=False, default="claude-sonnet-4-6")
    llm_temperature = Column(Float, nullable=False, default=0.7)
    llm_api_key_encrypted = Column(Text, nullable=False, default="")
    max_tokens_per_action = Column(Integer, nullable=False, default=4096)
    daily_cost_budget_usd = Column(Float, nullable=False, default=10.0)

    # Platform tokens (all Fernet-encrypted)
    telegram_token_encrypted = Column(Text, nullable=False, default="")
    discord_token_encrypted = Column(Text, nullable=False, default="")
    lark_app_id_encrypted = Column(Text, nullable=False, default="")
    lark_app_secret_encrypted = Column(Text, nullable=False, default="")
    slack_bot_token_encrypted = Column(Text, nullable=False, default="")
    slack_app_token_encrypted = Column(Text, nullable=False, default="")

    # Platform selection
    platform_type = Column(String, nullable=False, default="")

    # Behavior + Safety as JSON
    behavior_config = Column(Text, nullable=False, default="{}")
    safety_config = Column(Text, nullable=False, default="{}")

    # Memory config
    embedding_model = Column(String, nullable=False, default="text-embedding-3-small")
    max_retrieval_results = Column(Integer, nullable=False, default=10)
    importance_decay_days = Column(Integer, nullable=False, default=90)

    # Sandbox config
    sandbox_enabled = Column(Boolean, nullable=False, default=True)
    e2b_sandbox_id = Column(String, nullable=False, default="")

    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class MemoryRecord(Base):
    __tablename__ = "memories"

    id = Column(String, primary_key=True)
    agent_id = Column(String, nullable=False, default="default", index=True)
    content = Column(Text, nullable=False)
    scope = Column(String, nullable=False, index=True)
    scope_id = Column(String, nullable=False, default="", index=True)
    source = Column(String, nullable=False, default="")
    importance = Column(Float, nullable=False, default=0.5)
    created_at = Column(DateTime(timezone=True), nullable=False)
    metadata_json = Column(Text, nullable=False, default="{}")

    __table_args__ = (
        Index("ix_memories_scope_scope_id", "scope", "scope_id"),
        Index("ix_memories_agent_scope", "agent_id", "scope"),
    )


class ScheduledJobRecord(Base):
    """Persistent scheduled job definition."""

    __tablename__ = "scheduled_jobs"

    id = Column(String, primary_key=True)
    agent_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    schedule_type = Column(String, nullable=False)  # "cron" | "interval" | "once"
    schedule_expr = Column(String, nullable=False)  # cron expr, seconds, or ISO timestamp
    timezone = Column(String, nullable=False, default="UTC")
    prompt = Column(Text, nullable=False)
    channel_id = Column(String, nullable=False, default="")
    delivery_platform = Column(String, nullable=False, default="")
    delivery_chat_id = Column(String, nullable=False, default="")
    isolated = Column(Boolean, nullable=False, default=False)
    enabled = Column(Boolean, nullable=False, default=True)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    last_run_status = Column(String, nullable=True)  # "success" | "error"
    last_run_error = Column(Text, nullable=True)
    next_run_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    metadata_json = Column(Text, nullable=False, default="{}")


class ThreadMetaRecord(Base):
    __tablename__ = "thread_meta"

    thread_id = Column(String, primary_key=True)
    agent_id = Column(String, nullable=False, default="default", index=True)
    title = Column(Text, nullable=False, default="")
    created_at = Column(String, nullable=False, default="")
    user_id = Column(String, nullable=True, index=True)


class TokenUsageRecord(Base):
    """Per-request token usage tracking."""

    __tablename__ = "token_usage"

    id = Column(String, primary_key=True)
    agent_id = Column(String, nullable=False, index=True)
    thread_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=False, default="", index=True)
    input_tokens = Column(sqlalchemy.Integer, nullable=False, default=0)
    output_tokens = Column(sqlalchemy.Integer, nullable=False, default=0)
    total_tokens = Column(sqlalchemy.Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_token_usage_agent_thread", "agent_id", "thread_id"),)


class UserRecord(Base):
    """Dashboard user account."""

    __tablename__ = "users"

    id = Column(String, primary_key=True)
    email = Column(String, nullable=False, unique=True, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, default="user")  # admin | user
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class UserAgentAccess(Base):
    """Many-to-many: which users can access which agents."""

    __tablename__ = "user_agent_access"

    user_id = Column(String, primary_key=True)
    agent_id = Column(String, primary_key=True)

    __table_args__ = (
        Index("ix_user_agent_access_user", "user_id"),
        Index("ix_user_agent_access_agent", "agent_id"),
    )


class MemoryStore:
    """Persistent memory store with 3-layer isolation and per-agent scoping."""

    def __init__(self, database_url: str, agent_id: str = "default"):
        # Use default psycopg2 driver (not psycopg v3) to avoid
        # prepared statement caching conflicts with LangGraph
        sa_url = database_url
        if sa_url.startswith("postgresql+psycopg://"):
            sa_url = sa_url.replace("postgresql+psycopg://", "postgresql://", 1)
        self.engine = create_engine(
            sa_url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )
        self._session_factory = sessionmaker(bind=self.engine)
        self.agent_id = agent_id

    def initialize(self) -> None:
        """Verify database connection. Tables managed by Alembic migrations."""
        # Verify connection works
        with self.engine.connect() as conn:
            conn.execute(sqlalchemy.text("SELECT 1"))
        logger.info("Memory store initialized")

    def _session(self) -> Session:
        return self._session_factory()

    def store(self, entry: MemoryEntry) -> None:
        """Store a memory entry using raw SQL to avoid psycopg3/LangGraph conflicts."""
        with self.engine.connect() as conn:
            conn.execute(
                sqlalchemy.text(
                    "INSERT INTO memories "
                    "(id, agent_id, content, scope, scope_id, source, "
                    "importance, created_at, metadata_json) "
                    "VALUES (:id, :agent_id, :content, :scope, :scope_id, "
                    ":source, :importance, :created_at, :metadata_json) "
                    "ON CONFLICT (id) DO UPDATE SET "
                    "content = :content, importance = :importance"
                ),
                {
                    "id": entry.id,
                    "agent_id": self.agent_id,
                    "content": entry.content,
                    "scope": entry.scope.value,
                    "scope_id": entry.scope_id,
                    "source": entry.source,
                    "importance": entry.importance,
                    "created_at": entry.created_at,
                    "metadata_json": json.dumps(entry.metadata),
                },
            )
            conn.commit()

    def recall(
        self,
        query: str,
        scope: MemoryScope | None = None,
        scope_id: str | None = None,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        """Recall memories matching a query within the given scope.

        For now, uses simple text search. Phase 2 will add vector/embedding search.
        """
        with self._session() as session:
            q = session.query(MemoryRecord).filter(MemoryRecord.agent_id == self.agent_id)

            if scope is not None:
                q = q.filter(MemoryRecord.scope == scope.value)
            if scope_id is not None:
                q = q.filter(MemoryRecord.scope_id == scope_id)

            # Simple keyword matching for Phase 1
            # Phase 2: replace with pgvector similarity search
            search_terms = query.lower().split()
            for term in search_terms[:5]:  # limit to 5 terms
                q = q.filter(MemoryRecord.content.ilike(f"%{term}%"))

            q = q.order_by(MemoryRecord.importance.desc(), MemoryRecord.created_at.desc())
            q = q.limit(limit)

            results = []
            for record in q.all():
                results.append(
                    MemoryEntry(
                        id=record.id,
                        content=record.content,
                        scope=MemoryScope(record.scope),
                        scope_id=record.scope_id,
                        source=record.source,
                        importance=record.importance,
                        created_at=record.created_at,
                        metadata=json.loads(record.metadata_json),
                    )
                )
            return results

    def get_context_memories(
        self,
        scope: MemoryScope,
        scope_id: str = "",
        limit: int = 20,
    ) -> list[MemoryEntry]:
        """Get recent memories for a given context (channel or DM)."""
        with self._session() as session:
            q = (
                session.query(MemoryRecord)
                .filter(MemoryRecord.agent_id == self.agent_id)
                .filter(MemoryRecord.scope == scope.value)
                .filter(MemoryRecord.scope_id == scope_id)
                .order_by(MemoryRecord.created_at.desc())
                .limit(limit)
            )

            results = []
            for record in q.all():
                results.append(
                    MemoryEntry(
                        id=record.id,
                        content=record.content,
                        scope=MemoryScope(record.scope),
                        scope_id=record.scope_id,
                        source=record.source,
                        importance=record.importance,
                        created_at=record.created_at,
                        metadata=json.loads(record.metadata_json),
                    )
                )
            return results

    def forget(self, memory_id: str) -> bool:
        """Delete a specific memory."""
        with self._session() as session:
            record = (
                session.query(MemoryRecord).filter_by(id=memory_id, agent_id=self.agent_id).first()
            )
            if record:
                session.delete(record)
                session.commit()
                return True
            return False

    def count(self, scope: MemoryScope | None = None) -> int:
        """Count memories, optionally filtered by scope."""
        with self._session() as session:
            q = session.query(MemoryRecord).filter(MemoryRecord.agent_id == self.agent_id)
            if scope is not None:
                q = q.filter(MemoryRecord.scope == scope.value)
            return q.count()
