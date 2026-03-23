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
)
from sqlalchemy.orm import DeclarativeBase, Session

from core.database import get_engine, get_session_factory

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
        self.engine = get_engine(database_url)
        self._session_factory = get_session_factory(database_url)
        self.agent_id = agent_id
        self._embedding_cache: dict[str, list[float]] = {}

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

    @staticmethod
    def _record_to_entry(record: MemoryRecord) -> MemoryEntry:
        """Convert a DB record to a MemoryEntry."""
        return MemoryEntry(
            id=record.id,
            content=record.content,
            scope=MemoryScope(record.scope),
            scope_id=record.scope_id,
            source=record.source,
            importance=record.importance,
            created_at=record.created_at,
            metadata=json.loads(record.metadata_json),
        )

    def recall(
        self,
        query: str,
        scope: MemoryScope | None = None,
        scope_id: str | None = None,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        """Recall memories using hybrid search (BM25 full-text + vector + RRF fusion).

        Falls back to keyword search if full-text/vector columns are not yet available.
        """
        try:
            return self._recall_hybrid(query, scope, scope_id, limit)
        except Exception as e:
            logger.debug(f"Hybrid search unavailable, falling back to keyword: {e}")
            return self._recall_keyword(query, scope, scope_id, limit)

    def _recall_keyword(
        self,
        query: str,
        scope: MemoryScope | None = None,
        scope_id: str | None = None,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        """Phase 1 keyword fallback: ILIKE matching."""
        with self._session() as session:
            q = session.query(MemoryRecord).filter(MemoryRecord.agent_id == self.agent_id)

            if scope is not None:
                q = q.filter(MemoryRecord.scope == scope.value)
            if scope_id is not None:
                q = q.filter(MemoryRecord.scope_id == scope_id)

            search_terms = query.lower().split()
            for term in search_terms[:5]:
                q = q.filter(MemoryRecord.content.ilike(f"%{term}%"))

            q = q.order_by(MemoryRecord.importance.desc(), MemoryRecord.created_at.desc())
            q = q.limit(limit)

            return [self._record_to_entry(r) for r in q.all()]

    def _recall_hybrid(
        self,
        query: str,
        scope: MemoryScope | None = None,
        scope_id: str | None = None,
        limit: int = 10,
        rrf_k: int = 60,
    ) -> list[MemoryEntry]:
        """Hybrid search: BM25 full-text + pgvector cosine similarity + RRF fusion.

        Reciprocal Rank Fusion (RRF) combines rankings from both search methods:
            RRF_score(d) = 1/(k + rank_bm25(d)) + 1/(k + rank_vector(d))

        Args:
            query: Search query text.
            scope: Optional memory scope filter.
            scope_id: Optional scope ID filter.
            limit: Max results to return.
            rrf_k: RRF constant (default 60, higher = more weight to lower-ranked results).
        """
        # Build scope filter clause
        scope_clauses = ["agent_id = :agent_id"]
        params: dict[str, Any] = {"agent_id": self.agent_id, "limit": limit, "rrf_k": rrf_k}

        if scope is not None:
            scope_clauses.append("scope = :scope")
            params["scope"] = scope.value
        if scope_id is not None:
            scope_clauses.append("scope_id = :scope_id")
            params["scope_id"] = scope_id

        where_clause = " AND ".join(scope_clauses)

        # Prepare full-text query: sanitize terms and join with &
        import re

        sanitized = [
            re.sub(r"[^a-z0-9]", "", term) for term in query.lower().split()[:10] if term.strip()
        ]
        sanitized = [t for t in sanitized if t]
        ts_terms = " & ".join(f"{t}:*" for t in sanitized) if sanitized else "a:*"
        params["ts_query"] = ts_terms

        # Generate embedding for vector search
        try:
            embedding = self._get_embedding(query)
            params["embedding"] = str(embedding)
            has_vector = True
        except Exception as e:
            logger.debug(f"Embedding generation failed, using BM25 only: {e}")
            has_vector = False

        if has_vector:
            # Full hybrid: BM25 + vector with RRF
            sql = f"""
            WITH bm25_results AS (
                SELECT id, content, scope, scope_id, source,
                       importance, created_at, metadata_json,
                       ROW_NUMBER() OVER (
                           ORDER BY ts_rank_cd(content_tsv,
                           to_tsquery('english', :ts_query)) DESC
                       ) AS rank
                FROM memories
                WHERE {where_clause}
                  AND content_tsv @@ to_tsquery('english', :ts_query)
                LIMIT :limit * 3
            ),
            vector_results AS (
                SELECT id, content, scope, scope_id, source,
                       importance, created_at, metadata_json,
                       ROW_NUMBER() OVER (
                           ORDER BY content_embedding <=> :embedding::vector
                       ) AS rank
                FROM memories
                WHERE {where_clause}
                  AND content_embedding IS NOT NULL
                LIMIT :limit * 3
            ),
            fused AS (
                SELECT
                    COALESCE(b.id, v.id) AS id,
                    COALESCE(b.content, v.content) AS content,
                    COALESCE(b.scope, v.scope) AS scope,
                    COALESCE(b.scope_id, v.scope_id) AS scope_id,
                    COALESCE(b.source, v.source) AS source,
                    COALESCE(b.importance, v.importance) AS importance,
                    COALESCE(b.created_at, v.created_at) AS created_at,
                    COALESCE(b.metadata_json, v.metadata_json)
                        AS metadata_json,
                    COALESCE(1.0 / (:rrf_k + b.rank), 0)
                        + COALESCE(1.0 / (:rrf_k + v.rank), 0)
                        AS rrf_score
                FROM bm25_results b
                FULL OUTER JOIN vector_results v ON b.id = v.id
            )
            SELECT * FROM fused
            ORDER BY rrf_score DESC
            LIMIT :limit
            """
        else:
            # BM25 only
            sql = f"""
            SELECT id, content, scope, scope_id, source, importance, created_at, metadata_json
            FROM memories
            WHERE {where_clause}
              AND content_tsv @@ to_tsquery('english', :ts_query)
            ORDER BY ts_rank_cd(content_tsv, to_tsquery('english', :ts_query)) DESC
            LIMIT :limit
            """

        with self.engine.connect() as conn:
            rows = conn.execute(sqlalchemy.text(sql), params).fetchall()

        entries = []
        for row in rows:
            entries.append(
                MemoryEntry(
                    id=row.id,
                    content=row.content,
                    scope=MemoryScope(row.scope),
                    scope_id=row.scope_id,
                    source=row.source,
                    importance=row.importance,
                    created_at=row.created_at,
                    metadata=json.loads(row.metadata_json) if row.metadata_json else {},
                )
            )
        return entries

    _EMBEDDING_CACHE_MAX = 1000

    def _get_embedding(self, text: str) -> list[float]:
        """Generate an embedding vector for text using OpenAI's API.

        Uses an LRU-style cache to avoid redundant API calls.
        """
        import hashlib

        cache_key = hashlib.md5(text.encode()).hexdigest()
        if cache_key in self._embedding_cache:
            return self._embedding_cache[cache_key]

        import os

        import openai

        client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
        )
        embedding = response.data[0].embedding

        # Evict oldest entries when cache is full (FIFO approximation)
        if len(self._embedding_cache) >= self._EMBEDDING_CACHE_MAX:
            # Remove first 10% of entries
            evict_count = max(1, self._EMBEDDING_CACHE_MAX // 10)
            keys_to_remove = list(self._embedding_cache.keys())[:evict_count]
            for k in keys_to_remove:
                del self._embedding_cache[k]
        self._embedding_cache[cache_key] = embedding

        return embedding

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

            return [self._record_to_entry(r) for r in q.all()]

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
