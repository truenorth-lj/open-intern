"""Configuration loading and validation."""

from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# --- Nested config models (used when building per-agent config from DB) ---


class IdentityConfig(BaseModel):
    name: str = "Rin"
    role: str = "AI Employee"
    personality: str = "You are a helpful AI employee."
    avatar_url: str = ""


class LLMConfig(BaseModel):
    provider: str = "claude"  # claude | openai | minimax | ollama
    model: str = "claude-sonnet-4-6"
    api_key: str = ""
    temperature: float = 0.7
    max_tokens_per_action: int = 4096
    daily_cost_budget_usd: float = 10.0


class MemoryConfig(BaseModel):
    embedding_model: str = "text-embedding-3-small"
    max_retrieval_results: int = 10
    importance_decay_days: int = 90


class ProactivityConfig(BaseModel):
    enabled: bool = False
    heartbeat_interval_minutes: int = 10
    max_actions_per_hour: int = 3
    confidence_threshold: float = 0.8
    quiet_hours: str = "22:00-08:00"


class DailySummaryConfig(BaseModel):
    enabled: bool = False
    time: str = "17:00"
    channel: str = "general"


class BehaviorConfig(BaseModel):
    proactivity: ProactivityConfig = Field(default_factory=ProactivityConfig)
    daily_summary: DailySummaryConfig = Field(default_factory=DailySummaryConfig)


class SafetyConfig(BaseModel):
    require_approval_for: list[str] = Field(
        default_factory=lambda: [
            "send_email",
            "create_pr",
            "post_public_channel",
            "delete_anything",
        ]
    )
    auto_allow: list[str] = Field(
        default_factory=lambda: [
            "read_channel",
            "respond_to_mention",
            "respond_to_dm",
            "internal_note",
        ]
    )


# --- App-level config (infra-only, from .env / environment) ---


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # Infrastructure
    database_url: str = "postgresql://open_intern:open_intern@localhost:5556/open_intern"
    api_secret_key: str = ""
    port: int = 8000
    encryption_key: str = ""

    # Auth
    auth_secret: str = ""
    admin_email: str = "admin@open-intern.local"
    dashboard_password: str = ""

    # Shared infra keys
    e2b_api_key: str = ""

    # Sentry error tracking (opt-in — no data sent when DSN is empty)
    sentry_dsn: str = ""
    sentry_environment: str = "production"
    sentry_traces_sample_rate: float = 0.1
    sentry_profiles_sample_rate: float = 0.1

    # Cloudflare R2 backup (S3-compatible)
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = "open-intern-backups"

    # Per-agent config (built by AgentManager from DB, not from .env)
    identity: IdentityConfig = Field(default_factory=IdentityConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    behavior: BehaviorConfig = Field(default_factory=BehaviorConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)


_config: AppConfig | None = None


def get_config() -> AppConfig:
    """Get the global config singleton."""
    global _config
    if _config is None:
        _config = AppConfig()
    return _config


def set_config(config: AppConfig) -> None:
    """Override global config (useful for testing)."""
    global _config
    _config = config
