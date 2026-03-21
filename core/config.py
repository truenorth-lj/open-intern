"""Configuration loading and validation."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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


class TelegramConfig(BaseModel):
    bot_token: str = ""


class PlatformConfig(BaseModel):
    primary: str = "lark"
    lark: LarkConfig = Field(default_factory=LarkConfig)
    discord: DiscordConfig = Field(default_factory=DiscordConfig)
    slack: SlackConfig = Field(default_factory=SlackConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)


class LLMConfig(BaseModel):
    provider: str = "claude"  # claude | openai | minimax | ollama
    model: str = "claude-sonnet-4-6"
    api_key: str = ""  # optional; falls back to env vars
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


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # --- Environment variables (flat, auto-mapped from .env / os.environ) ---
    database_url: str = "postgresql://open_intern:open_intern@localhost:5556/open_intern"
    platform: str = ""  # overrides platform.primary when set
    api_secret_key: str = ""
    port: int = 8000

    # API keys
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    minimax_api_key: str = ""

    # Platform tokens (env var overrides YAML)
    telegram_bot_token: str = ""
    discord_bot_token: str = ""

    # --- Nested configs (from YAML) ---
    identity: IdentityConfig = Field(default_factory=IdentityConfig)
    platform_config: PlatformConfig = Field(default_factory=PlatformConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    behavior: BehaviorConfig = Field(default_factory=BehaviorConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)

    @property
    def active_platform(self) -> str:
        """Return the effective platform: env var > YAML config."""
        return self.platform or self.platform_config.primary

    @property
    def effective_telegram_token(self) -> str:
        """Return telegram token: env var > YAML config."""
        return self.telegram_bot_token or self.platform_config.telegram.bot_token

    @property
    def effective_discord_token(self) -> str:
        """Return discord token: env var > YAML config."""
        return self.discord_bot_token or self.platform_config.discord.bot_token


def load_config(path: str | Path | None = None) -> AppConfig:
    """Load config from YAML file, then let pydantic-settings overlay env vars."""
    search_paths = [
        Path(path) if path else None,
        Path("config/agent.yaml"),
        Path("agent.yaml"),
        Path.home() / ".open_intern" / "agent.yaml",
    ]

    yaml_data: dict = {}
    for p in search_paths:
        if p and p.exists():
            yaml_data = yaml.safe_load(p.read_text()) or {}
            break

    # Remap YAML "platform" (nested object) to "platform_config"
    if "platform" in yaml_data and isinstance(yaml_data["platform"], dict):
        yaml_data["platform_config"] = yaml_data.pop("platform")

    # BaseSettings: YAML values as init kwargs, env vars auto-override
    return AppConfig(**yaml_data)


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
