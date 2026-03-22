"""Tests for agent config in DB with encryption."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from cryptography.fernet import Fernet

from core.config import AppConfig, BehaviorConfig, SafetyConfig
from core.crypto import decrypt, encrypt
from memory.store import AgentRecord, SystemSettingRecord

# --- Fixtures ---

TEST_KEY = Fernet.generate_key().decode()


@pytest.fixture(autouse=True)
def set_encryption_key(monkeypatch):
    """Ensure ENCRYPTION_KEY is set for all tests."""
    monkeypatch.setenv("ENCRYPTION_KEY", TEST_KEY)


# --- Crypto tests ---


class TestCrypto:
    def test_encrypt_decrypt_roundtrip(self):
        plaintext = "sk-ant-secret-key-12345"
        ciphertext = encrypt(plaintext)
        assert ciphertext != plaintext
        assert ciphertext != ""
        assert decrypt(ciphertext) == plaintext

    def test_encrypt_empty_returns_empty(self):
        assert encrypt("") == ""

    def test_decrypt_empty_returns_empty(self):
        assert decrypt("") == ""

    def test_encrypt_produces_different_ciphertext_each_time(self):
        plaintext = "same-value"
        c1 = encrypt(plaintext)
        c2 = encrypt(plaintext)
        # Fernet includes a timestamp, so ciphertexts differ
        assert c1 != c2
        # But both decrypt to the same value
        assert decrypt(c1) == plaintext
        assert decrypt(c2) == plaintext

    def test_missing_key_raises(self, monkeypatch):
        from core.crypto import reset_fernet_cache

        reset_fernet_cache()
        monkeypatch.delenv("ENCRYPTION_KEY")
        with pytest.raises(Exception, match="ENCRYPTION_KEY not set"):
            encrypt("test")
        reset_fernet_cache()


# --- AgentRecord schema tests ---


class TestAgentRecordSchema:
    def test_new_columns_exist(self):
        """Verify the new columns are present on AgentRecord."""
        now = datetime.now(timezone.utc)
        record = AgentRecord(
            agent_id="test-agent",
            name="Test",
            llm_api_key_encrypted=encrypt("sk-test"),
            max_tokens_per_action=8192,
            daily_cost_budget_usd=5.0,
            telegram_token_encrypted=encrypt("tg-token"),
            discord_token_encrypted=encrypt("dc-token"),
            lark_app_id_encrypted=encrypt("lark-id"),
            lark_app_secret_encrypted=encrypt("lark-secret"),
            slack_bot_token_encrypted="",
            slack_app_token_encrypted="",
            platform_type="telegram",
            behavior_config='{"proactivity": {"enabled": true}}',
            safety_config="{}",
            embedding_model="text-embedding-3-large",
            max_retrieval_results=20,
            importance_decay_days=30,
            created_at=now,
            updated_at=now,
        )

        assert record.agent_id == "test-agent"
        assert record.max_tokens_per_action == 8192
        assert record.daily_cost_budget_usd == 5.0
        assert record.platform_type == "telegram"
        assert record.embedding_model == "text-embedding-3-large"
        assert record.max_retrieval_results == 20
        assert record.importance_decay_days == 30

        # Encrypted fields should decrypt correctly
        assert decrypt(record.llm_api_key_encrypted) == "sk-test"
        assert decrypt(record.telegram_token_encrypted) == "tg-token"
        assert decrypt(record.discord_token_encrypted) == "dc-token"
        assert decrypt(record.lark_app_id_encrypted) == "lark-id"
        assert decrypt(record.lark_app_secret_encrypted) == "lark-secret"


class TestSystemSettingRecord:
    def test_setting_record_fields(self):
        now = datetime.now(timezone.utc)
        setting = SystemSettingRecord(
            key="default_llm_api_key",
            value=encrypt("sk-global-key"),
            is_secret=True,
            description="Default LLM API key for new agents",
            updated_at=now,
        )
        assert setting.key == "default_llm_api_key"
        assert setting.is_secret is True
        assert decrypt(setting.value) == "sk-global-key"


# --- AgentManager._build_agent_config tests ---


class TestBuildAgentConfig:
    def _make_record(self, **overrides):
        now = datetime.now(timezone.utc)
        defaults = {
            "agent_id": "test",
            "name": "TestBot",
            "role": "AI Employee",
            "personality": "Helpful.",
            "avatar_url": "",
            "llm_provider": "claude",
            "llm_model": "claude-sonnet-4-6",
            "llm_temperature": 0.7,
            "llm_api_key_encrypted": encrypt("sk-agent-key"),
            "max_tokens_per_action": 4096,
            "daily_cost_budget_usd": 10.0,
            "telegram_token_encrypted": "",
            "discord_token_encrypted": "",
            "lark_app_id_encrypted": "",
            "lark_app_secret_encrypted": "",
            "slack_bot_token_encrypted": "",
            "slack_app_token_encrypted": "",
            "platform_type": "",
            "behavior_config": "{}",
            "safety_config": "{}",
            "embedding_model": "text-embedding-3-small",
            "max_retrieval_results": 10,
            "importance_decay_days": 90,
            "sandbox_enabled": True,
            "e2b_sandbox_id": "",
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }
        defaults.update(overrides)
        return AgentRecord(**defaults)

    def _make_manager(self):
        from core.manager import AgentManager

        mgr = AgentManager.__new__(AgentManager)
        mgr.config = AppConfig(
            database_url="postgresql://test:test@localhost/test",
            api_secret_key="test-secret",
            port=8000,
            encryption_key=TEST_KEY,
            e2b_api_key="e2b_test",
        )
        mgr._agents = {}
        mgr._scheduler = None
        # Mock DB session for system settings lookups
        session = MagicMock()
        session.__enter__ = MagicMock(return_value=session)
        session.__exit__ = MagicMock(return_value=False)
        session.query.return_value.filter_by.return_value.first.return_value = (
            None  # no system setting
        )
        mgr._session_factory = MagicMock(return_value=session)
        mgr._engine = MagicMock()
        return mgr

    def test_builds_config_with_decrypted_key(self):
        mgr = self._make_manager()
        rec = self._make_record()
        config = mgr._build_agent_config(rec)

        assert isinstance(config, AppConfig)
        assert config.identity.name == "TestBot"
        assert config.llm.provider == "claude"
        assert config.llm.model == "claude-sonnet-4-6"
        assert config.llm.api_key == "sk-agent-key"
        assert config.llm.max_tokens_per_action == 4096
        assert config.memory.embedding_model == "text-embedding-3-small"

    def test_falls_back_to_system_default_key(self):
        mgr = self._make_manager()
        rec = self._make_record(llm_api_key_encrypted="")

        # Mock system setting to return a default key
        setting = MagicMock()
        setting.value = encrypt("sk-system-default")
        session = MagicMock()
        session.__enter__ = MagicMock(return_value=session)
        session.__exit__ = MagicMock(return_value=False)
        session.query.return_value.filter_by.return_value.first.return_value = setting
        mgr._session_factory = MagicMock(return_value=session)

        config = mgr._build_agent_config(rec)
        assert config.llm.api_key == "sk-system-default"

    def test_behavior_config_parsed(self):
        mgr = self._make_manager()
        rec = self._make_record(
            behavior_config='{"proactivity": {"enabled": true, "max_actions_per_hour": 5}}'
        )
        config = mgr._build_agent_config(rec)
        assert config.behavior.proactivity.enabled is True
        assert config.behavior.proactivity.max_actions_per_hour == 5

    def test_safety_config_parsed(self):
        mgr = self._make_manager()
        safety = '{"require_approval_for": ["delete_anything"], "auto_allow": ["read_channel"]}'
        rec = self._make_record(safety_config=safety)
        config = mgr._build_agent_config(rec)
        assert config.safety.require_approval_for == ["delete_anything"]
        assert config.safety.auto_allow == ["read_channel"]

    def test_invalid_json_uses_defaults(self):
        mgr = self._make_manager()
        rec = self._make_record(behavior_config="not json", safety_config="")
        config = mgr._build_agent_config(rec)
        assert isinstance(config.behavior, BehaviorConfig)
        assert isinstance(config.safety, SafetyConfig)


# --- AppConfig tests ---


class TestAppConfig:
    def test_infra_only_fields(self):
        config = AppConfig(
            database_url="postgresql://test:test@localhost/test",
            encryption_key="test-key",
            e2b_api_key="e2b_xxx",
        )
        assert config.database_url == "postgresql://test:test@localhost/test"
        assert config.encryption_key == "test-key"
        assert config.e2b_api_key == "e2b_xxx"

    def test_no_legacy_fields(self):
        """Verify removed fields are gone."""
        config = AppConfig()
        assert not hasattr(config, "anthropic_api_key")
        assert not hasattr(config, "openai_api_key")
        assert not hasattr(config, "minimax_api_key")
        assert not hasattr(config, "telegram_bot_token")
        assert not hasattr(config, "discord_bot_token")
        assert not hasattr(config, "platform_config")
        assert not hasattr(config, "platform")
        assert not hasattr(config, "active_platform")
