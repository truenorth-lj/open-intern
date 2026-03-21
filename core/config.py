"""Configuration loading and validation."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class IdentityConfig(BaseModel):
    name: str = "Rin"
    role: str = "AI Employee"
    personality: str = "You are a helpful AI employee."
    avatar_url: str = ""


class LarkConfig(BaseModel):
    app_id: str = ""
    app_secret: str = ""


class DiscordConfig(BaseModel):
    bot_token: str = ""


class SlackConfig(BaseModel):
    bot_token: str = ""
    app_token: str = ""


class PlatformConfig(BaseModel):
    primary: str = "lark"
    lark: LarkConfig = Field(default_factory=LarkConfig)
    discord: DiscordConfig = Field(default_factory=DiscordConfig)
    slack: SlackConfig = Field(default_factory=SlackConfig)


class LLMConfig(BaseModel):
    provider: str = "claude"  # claude | openai | minimax | ollama
    model: str = "claude-sonnet-4-6"
    api_key: str = ""  # optional; falls back to ANTHROPIC/OPENAI/MINIMAX_API_KEY env vars
    temperature: float = 0.7
    max_tokens_per_action: int = 4096
    daily_cost_budget_usd: float = 10.0


class MemoryConfig(BaseModel):
    database_url: str = Field(
        default_factory=lambda: os.environ.get(
            "DATABASE_URL", "postgresql://open_intern:open_intern@localhost:5556/open_intern"
        )
    )
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


class AppConfig(BaseModel):
    identity: IdentityConfig = Field(default_factory=IdentityConfig)
    platform: PlatformConfig = Field(default_factory=PlatformConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    behavior: BehaviorConfig = Field(default_factory=BehaviorConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)


def load_config(path: str | Path | None = None) -> AppConfig:
    """Load config from YAML file. Falls back to defaults if not found."""
    search_paths = [
        Path(path) if path else None,
        Path("config/agent.yaml"),
        Path("agent.yaml"),
        Path.home() / ".open_intern" / "agent.yaml",
    ]

    config = AppConfig()
    for p in search_paths:
        if p and p.exists():
            raw = yaml.safe_load(p.read_text())
            config = AppConfig.model_validate(raw or {})
            break

    # Environment variables override YAML config
    if db_url := os.environ.get("DATABASE_URL"):
        config.memory.database_url = db_url

    return config


_config: AppConfig | None = None


def get_config() -> AppConfig:
    """Get the global config singleton."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def set_config(config: AppConfig) -> None:
    """Override global config (useful for testing)."""
    global _config
    _config = config
