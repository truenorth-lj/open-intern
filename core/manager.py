"""Agent Manager — manages multiple agent instances with DB-backed configuration."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.agent import OpenInternAgent
from core.config import AppConfig, IdentityConfig, LLMConfig
from memory.store import AgentRecord, Base

logger = logging.getLogger(__name__)


class AgentManager:
    """Manages lifecycle of multiple OpenInternAgent instances backed by DB."""

    def __init__(self, config: AppConfig):
        self.config = config
        self._agents: dict[str, OpenInternAgent] = {}

        # DB connection for agent registry
        db_url = config.database_url
        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
        self._engine = create_engine(db_url, pool_size=5, max_overflow=10, pool_pre_ping=True)
        self._session_factory = sessionmaker(bind=self._engine)

    def initialize(self) -> None:
        """Create tables and load all active agents from DB."""
        Base.metadata.create_all(self._engine)
        self._load_agents()

    def _load_agents(self) -> None:
        """Load and initialize all active agents from DB."""
        with self._session_factory() as session:
            records = session.query(AgentRecord).filter_by(is_active=True).all()
            for rec in records:
                try:
                    self._init_agent_from_record(rec)
                    logger.info(f"Loaded agent: {rec.agent_id} ({rec.name})")
                except Exception as e:
                    logger.error(f"Failed to load agent {rec.agent_id}: {e}")

    def _init_agent_from_record(self, rec: AgentRecord) -> OpenInternAgent:
        """Create and initialize an OpenInternAgent from a DB record."""
        agent_config = self._build_agent_config(rec)
        agent = OpenInternAgent(agent_config, agent_id=rec.agent_id)
        agent.initialize()
        self._agents[rec.agent_id] = agent
        return agent

    def _build_agent_config(self, rec: AgentRecord) -> AppConfig:
        """Build an AppConfig tailored for a specific agent."""
        # Start from the global config and override agent-specific fields
        base = self.config.model_dump()
        base["identity"] = IdentityConfig(
            name=rec.name,
            role=rec.role,
            personality=rec.personality,
            avatar_url=rec.avatar_url,
        ).model_dump()
        base["llm"] = LLMConfig(
            provider=rec.llm_provider,
            model=rec.llm_model,
            temperature=rec.llm_temperature,
        ).model_dump()
        # Preserve API keys from global config
        return AppConfig(**base)

    def get(self, agent_id: str) -> OpenInternAgent | None:
        """Get an initialized agent by ID."""
        return self._agents.get(agent_id)

    def list_agents(self) -> list[dict]:
        """List all registered agents from DB."""
        with self._session_factory() as session:
            records = session.query(AgentRecord).order_by(AgentRecord.created_at).all()
            return [
                {
                    "agent_id": r.agent_id,
                    "name": r.name,
                    "role": r.role,
                    "personality": r.personality,
                    "avatar_url": r.avatar_url,
                    "llm_provider": r.llm_provider,
                    "llm_model": r.llm_model,
                    "llm_temperature": r.llm_temperature,
                    "telegram_token": "***" if r.telegram_token else "",
                    "is_active": r.is_active,
                    "created_at": r.created_at.isoformat() if r.created_at else "",
                    "updated_at": r.updated_at.isoformat() if r.updated_at else "",
                }
                for r in records
            ]

    def create_agent(
        self,
        agent_id: str,
        name: str,
        role: str = "AI Employee",
        personality: str = "You are a helpful AI employee.",
        avatar_url: str = "",
        llm_provider: str = "claude",
        llm_model: str = "claude-sonnet-4-6",
        llm_temperature: float = 0.7,
        telegram_token: str = "",
    ) -> dict:
        """Create a new agent in DB and initialize it."""
        now = datetime.now(timezone.utc)
        record = AgentRecord(
            agent_id=agent_id,
            name=name,
            role=role,
            personality=personality,
            avatar_url=avatar_url,
            llm_provider=llm_provider,
            llm_model=llm_model,
            llm_temperature=llm_temperature,
            telegram_token=telegram_token,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        with self._session_factory() as session:
            existing = session.query(AgentRecord).filter_by(agent_id=agent_id).first()
            if existing:
                raise ValueError(f"Agent '{agent_id}' already exists")
            session.add(record)
            session.commit()

        # Initialize the agent runtime
        self._init_agent_from_record(record)
        logger.info(f"Created agent: {agent_id} ({name})")
        return {"agent_id": agent_id, "name": name, "status": "active"}

    def update_agent(self, agent_id: str, **kwargs) -> dict:
        """Update agent fields in DB. Requires restart to apply runtime changes."""
        with self._session_factory() as session:
            record = session.query(AgentRecord).filter_by(agent_id=agent_id).first()
            if not record:
                raise ValueError(f"Agent '{agent_id}' not found")
            allowed_fields = {
                "name",
                "role",
                "personality",
                "avatar_url",
                "llm_provider",
                "llm_model",
                "llm_temperature",
                "telegram_token",
                "is_active",
            }
            for key, value in kwargs.items():
                if key in allowed_fields:
                    setattr(record, key, value)
            record.updated_at = datetime.now(timezone.utc)
            session.commit()
            agent_id_val = record.agent_id
        logger.info(f"Updated agent: {agent_id_val}")
        return {"agent_id": agent_id_val, "status": "updated"}

    def delete_agent(self, agent_id: str) -> dict:
        """Soft-delete an agent (set is_active=False) and stop its runtime."""
        # Stop runtime if running
        if agent_id in self._agents:
            del self._agents[agent_id]
        with self._session_factory() as session:
            record = session.query(AgentRecord).filter_by(agent_id=agent_id).first()
            if not record:
                raise ValueError(f"Agent '{agent_id}' not found")
            record.is_active = False
            record.updated_at = datetime.now(timezone.utc)
            session.commit()
        logger.info(f"Deactivated agent: {agent_id}")
        return {"agent_id": agent_id, "status": "deactivated"}

    def get_telegram_agents(self) -> dict[str, AgentRecord]:
        """Get all active agents that have a Telegram token configured."""
        with self._session_factory() as session:
            records = (
                session.query(AgentRecord)
                .filter_by(is_active=True)
                .filter(AgentRecord.telegram_token != "")
                .all()
            )
            # Detach from session so they can be used after session closes
            result = {}
            for r in records:
                session.expunge(r)
                result[r.agent_id] = r
            return result

    @property
    def agents(self) -> dict[str, OpenInternAgent]:
        return self._agents
