"""Agent Manager — manages multiple agent instances with DB-backed configuration."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.agent import OpenInternAgent
from core.config import (
    AppConfig,
    BehaviorConfig,
    IdentityConfig,
    LLMConfig,
    MemoryConfig,
    SafetyConfig,
)
from core.crypto import decrypt, encrypt
from memory.store import AgentRecord, SystemSettingRecord

if TYPE_CHECKING:
    from core.scheduler import CronScheduler

logger = logging.getLogger(__name__)

# Fields that contain encrypted secrets on AgentRecord
_ENCRYPTED_FIELDS = {
    "llm_api_key",
    "telegram_token",
    "discord_token",
    "lark_app_id",
    "lark_app_secret",
    "slack_bot_token",
    "slack_app_token",
}


class AgentManager:
    """Manages lifecycle of multiple OpenInternAgent instances backed by DB."""

    def __init__(self, config: AppConfig, scheduler: CronScheduler | None = None):
        self.config = config
        self._agents: dict[str, OpenInternAgent] = {}
        self._scheduler = scheduler

        # DB connection for agent registry
        db_url = config.database_url
        # Use psycopg2 (default) to avoid psycopg3 conflicts with LangGraph
        if db_url.startswith("postgresql+psycopg://"):
            db_url = db_url.replace("postgresql+psycopg://", "postgresql://", 1)
        self._engine = create_engine(
            db_url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )
        self._session_factory = sessionmaker(bind=self._engine)

    def initialize(self) -> None:
        """Load all active agents from DB. Tables managed by Alembic migrations."""
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

        extra_tools: list = []
        if self._scheduler:
            from core.scheduler import create_scheduler_tools

            extra_tools = create_scheduler_tools(self._scheduler, rec.agent_id)

        agent = OpenInternAgent(
            agent_config,
            agent_id=rec.agent_id,
            sandbox_enabled=rec.sandbox_enabled,
            e2b_sandbox_id=rec.e2b_sandbox_id,
            extra_tools=extra_tools,
        )
        agent.initialize()
        # Persist E2B sandbox ID back to DB if newly created
        if agent._e2b_backend and agent._e2b_backend.sandbox_id:
            self._update_sandbox_id(rec.agent_id, agent._e2b_backend.sandbox_id)
        self._agents[rec.agent_id] = agent
        return agent

    def _update_sandbox_id(self, agent_id: str, sandbox_id: str) -> None:
        """Save the E2B sandbox ID to DB for later resume."""
        with self._session_factory() as session:
            record = session.query(AgentRecord).filter_by(agent_id=agent_id).first()
            if record:
                record.e2b_sandbox_id = sandbox_id
                session.commit()

    def _resolve_llm_api_key(self, rec: AgentRecord) -> str:
        """Resolve LLM API key: agent's own > system default > empty."""
        # 1. Agent's own key
        agent_key = decrypt(rec.llm_api_key_encrypted)
        if agent_key:
            return agent_key
        # 2. System default
        return self._get_system_setting("default_llm_api_key", is_secret=True)

    def _get_system_setting(self, key: str, is_secret: bool = False) -> str:
        """Read a system setting from DB."""
        with self._session_factory() as session:
            setting = session.query(SystemSettingRecord).filter_by(key=key).first()
            if not setting:
                return ""
            if is_secret:
                return decrypt(setting.value)
            return setting.value

    def _build_agent_config(self, rec: AgentRecord) -> AppConfig:
        """Build an AppConfig tailored for a specific agent, decrypting secrets."""
        api_key = self._resolve_llm_api_key(rec)

        # Parse behavior/safety JSON, falling back to defaults
        try:
            behavior_data = json.loads(rec.behavior_config) if rec.behavior_config else {}
        except (json.JSONDecodeError, TypeError):
            behavior_data = {}
        try:
            safety_data = json.loads(rec.safety_config) if rec.safety_config else {}
        except (json.JSONDecodeError, TypeError):
            safety_data = {}

        identity = IdentityConfig(
            name=rec.name,
            role=rec.role,
            personality=rec.personality,
            avatar_url=rec.avatar_url,
        )
        llm = LLMConfig(
            provider=rec.llm_provider,
            model=rec.llm_model,
            temperature=rec.llm_temperature,
            api_key=api_key,
            max_tokens_per_action=rec.max_tokens_per_action,
            daily_cost_budget_usd=rec.daily_cost_budget_usd,
        )
        memory = MemoryConfig(
            embedding_model=rec.embedding_model,
            max_retrieval_results=rec.max_retrieval_results,
            importance_decay_days=rec.importance_decay_days,
        )
        behavior = BehaviorConfig(**behavior_data) if behavior_data else BehaviorConfig()
        safety = SafetyConfig(**safety_data) if safety_data else SafetyConfig()

        return AppConfig(
            database_url=self.config.database_url,
            api_secret_key=self.config.api_secret_key,
            port=self.config.port,
            encryption_key=self.config.encryption_key,
            e2b_api_key=self.config.e2b_api_key,
            identity=identity,
            llm=llm,
            memory=memory,
            behavior=behavior,
            safety=safety,
        )

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
                    "max_tokens_per_action": r.max_tokens_per_action,
                    "daily_cost_budget_usd": r.daily_cost_budget_usd,
                    "llm_api_key": "***" if r.llm_api_key_encrypted else "",
                    "telegram_token": "***" if r.telegram_token_encrypted else "",
                    "discord_token": "***" if r.discord_token_encrypted else "",
                    "lark_app_id": "***" if r.lark_app_id_encrypted else "",
                    "lark_app_secret": "***" if r.lark_app_secret_encrypted else "",
                    "slack_bot_token": "***" if r.slack_bot_token_encrypted else "",
                    "slack_app_token": "***" if r.slack_app_token_encrypted else "",
                    "platform_type": r.platform_type,
                    "behavior_config": r.behavior_config,
                    "safety_config": r.safety_config,
                    "embedding_model": r.embedding_model,
                    "max_retrieval_results": r.max_retrieval_results,
                    "importance_decay_days": r.importance_decay_days,
                    "sandbox_enabled": r.sandbox_enabled,
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
        llm_api_key: str = "",
        max_tokens_per_action: int = 4096,
        daily_cost_budget_usd: float = 10.0,
        telegram_token: str = "",
        discord_token: str = "",
        lark_app_id: str = "",
        lark_app_secret: str = "",
        slack_bot_token: str = "",
        slack_app_token: str = "",
        platform_type: str = "",
        behavior_config: str = "{}",
        safety_config: str = "{}",
        embedding_model: str = "text-embedding-3-small",
        max_retrieval_results: int = 10,
        importance_decay_days: int = 90,
        sandbox_enabled: bool = True,
    ) -> dict:
        """Create a new agent in DB and initialize it. Secrets are encrypted before storage."""
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
            llm_api_key_encrypted=encrypt(llm_api_key),
            max_tokens_per_action=max_tokens_per_action,
            daily_cost_budget_usd=daily_cost_budget_usd,
            telegram_token_encrypted=encrypt(telegram_token),
            discord_token_encrypted=encrypt(discord_token),
            lark_app_id_encrypted=encrypt(lark_app_id),
            lark_app_secret_encrypted=encrypt(lark_app_secret),
            slack_bot_token_encrypted=encrypt(slack_bot_token),
            slack_app_token_encrypted=encrypt(slack_app_token),
            platform_type=platform_type,
            behavior_config=behavior_config,
            safety_config=safety_config,
            embedding_model=embedding_model,
            max_retrieval_results=max_retrieval_results,
            importance_decay_days=importance_decay_days,
            sandbox_enabled=sandbox_enabled,
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
            # Expunge before session closes so record stays usable
            session.expunge(record)

        # Initialize the agent runtime (record is detached but fully loaded)
        self._init_agent_from_record(record)
        logger.info(f"Created agent: {agent_id} ({name})")
        return {"agent_id": agent_id, "name": name, "status": "active"}

    def update_agent(self, agent_id: str, **kwargs) -> dict:
        """Update agent fields in DB. Secrets are encrypted before storage."""
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
                "max_tokens_per_action",
                "daily_cost_budget_usd",
                "platform_type",
                "behavior_config",
                "safety_config",
                "embedding_model",
                "max_retrieval_results",
                "importance_decay_days",
                "sandbox_enabled",
                "is_active",
            }
            for key, value in kwargs.items():
                if key in _ENCRYPTED_FIELDS:
                    # Encrypt and store in the _encrypted column
                    setattr(record, f"{key}_encrypted", encrypt(value))
                elif key in allowed_fields:
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
                .filter(AgentRecord.telegram_token_encrypted != "")
                .all()
            )
            result = {}
            for r in records:
                session.expunge(r)
                result[r.agent_id] = r
            return result

    def get_discord_agents(self) -> dict[str, AgentRecord]:
        """Get all active agents that have a Discord token configured."""
        with self._session_factory() as session:
            records = (
                session.query(AgentRecord)
                .filter_by(is_active=True)
                .filter(AgentRecord.discord_token_encrypted != "")
                .all()
            )
            result = {}
            for r in records:
                session.expunge(r)
                result[r.agent_id] = r
            return result

    def get_lark_agents(self) -> dict[str, AgentRecord]:
        """Get all active agents that have Lark credentials configured."""
        with self._session_factory() as session:
            records = (
                session.query(AgentRecord)
                .filter_by(is_active=True)
                .filter(AgentRecord.lark_app_id_encrypted != "")
                .filter(AgentRecord.lark_app_secret_encrypted != "")
                .all()
            )
            result = {}
            for r in records:
                session.expunge(r)
                result[r.agent_id] = r
            return result

    # --- System Settings ---

    def get_system_settings(self) -> list[dict]:
        """List all system settings, redacting secrets."""
        with self._session_factory() as session:
            records = session.query(SystemSettingRecord).order_by(SystemSettingRecord.key).all()
            return [
                {
                    "key": r.key,
                    "value": "***" if r.is_secret and r.value else r.value,
                    "is_secret": r.is_secret,
                    "description": r.description,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else "",
                }
                for r in records
            ]

    def upsert_system_setting(
        self, key: str, value: str, is_secret: bool = False, description: str = ""
    ) -> dict:
        """Create or update a system setting. Encrypts value if is_secret."""
        stored_value = encrypt(value) if is_secret else value
        now = datetime.now(timezone.utc)
        with self._session_factory() as session:
            existing = session.query(SystemSettingRecord).filter_by(key=key).first()
            if existing:
                existing.value = stored_value
                existing.is_secret = is_secret
                if description:
                    existing.description = description
                existing.updated_at = now
            else:
                session.add(
                    SystemSettingRecord(
                        key=key,
                        value=stored_value,
                        is_secret=is_secret,
                        description=description,
                        updated_at=now,
                    )
                )
            session.commit()
        return {"key": key, "status": "updated"}

    def delete_system_setting(self, key: str) -> bool:
        """Delete a system setting. Returns True if deleted."""
        with self._session_factory() as session:
            record = session.query(SystemSettingRecord).filter_by(key=key).first()
            if not record:
                return False
            session.delete(record)
            session.commit()
            return True

    @property
    def agents(self) -> dict[str, OpenInternAgent]:
        return self._agents
