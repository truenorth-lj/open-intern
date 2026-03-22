"""Move agent config from YAML/.env to DB with encryption.

Creates system_settings table, expands agents table with encrypted secrets,
platform tokens, behavior/safety JSON, and memory config columns.
Migrates existing telegram_token data to telegram_token_encrypted.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-03-22 12:00:00.000000
"""

import logging
import os

import sqlalchemy as sa

from alembic import op

logger = logging.getLogger(__name__)

revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def _add_col(name, col_type, default=""):
    """Helper to add a column with server_default."""
    op.add_column(
        "agents",
        sa.Column(name, col_type, server_default=default, nullable=False),
    )


def upgrade() -> None:
    # --- Create system_settings table ---
    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "is_secret",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("key"),
    )

    # --- Add new columns to agents ---

    # LLM fields
    _add_col("llm_api_key_encrypted", sa.Text())
    _add_col("max_tokens_per_action", sa.Integer(), "4096")
    _add_col("daily_cost_budget_usd", sa.Float(), "10.0")

    # Platform tokens (encrypted)
    _add_col("telegram_token_encrypted", sa.Text())
    _add_col("discord_token_encrypted", sa.Text())
    _add_col("lark_app_id_encrypted", sa.Text())
    _add_col("lark_app_secret_encrypted", sa.Text())
    _add_col("slack_bot_token_encrypted", sa.Text())
    _add_col("slack_app_token_encrypted", sa.Text())

    # Platform selection
    _add_col("platform_type", sa.String())

    # Behavior + Safety JSON
    _add_col("behavior_config", sa.Text(), "{}")
    _add_col("safety_config", sa.Text(), "{}")

    # Memory config
    _add_col("embedding_model", sa.String(), "text-embedding-3-small")
    _add_col("max_retrieval_results", sa.Integer(), "10")
    _add_col("importance_decay_days", sa.Integer(), "90")

    # --- Migrate telegram_token -> telegram_token_encrypted ---
    encryption_key = os.environ.get("ENCRYPTION_KEY", "")
    if encryption_key:
        from cryptography.fernet import Fernet

        f = Fernet(encryption_key.encode())
        conn = op.get_bind()
        rows = conn.execute(
            sa.text("SELECT agent_id, telegram_token FROM agents WHERE telegram_token != ''")
        ).fetchall()
        for row in rows:
            encrypted = f.encrypt(row[1].encode()).decode()
            conn.execute(
                sa.text("UPDATE agents SET telegram_token_encrypted = :enc WHERE agent_id = :aid"),
                {"enc": encrypted, "aid": row[0]},
            )
    else:
        op.execute(
            "UPDATE agents SET telegram_token_encrypted = telegram_token WHERE telegram_token != ''"
        )

    # Drop the old plaintext column
    op.drop_column("agents", "telegram_token")


def downgrade() -> None:
    # Re-add old column
    op.add_column(
        "agents",
        sa.Column(
            "telegram_token",
            sa.String(),
            server_default="",
            nullable=False,
        ),
    )

    # Try to decrypt back (best effort)
    encryption_key = os.environ.get("ENCRYPTION_KEY", "")
    if encryption_key:
        from cryptography.fernet import Fernet

        f = Fernet(encryption_key.encode())
        conn = op.get_bind()
        rows = conn.execute(
            sa.text(
                "SELECT agent_id, telegram_token_encrypted "
                "FROM agents "
                "WHERE telegram_token_encrypted != ''"
            )
        ).fetchall()
        for row in rows:
            try:
                decrypted = f.decrypt(row[1].encode()).decode()
                conn.execute(
                    sa.text("UPDATE agents SET telegram_token = :tok WHERE agent_id = :aid"),
                    {"tok": decrypted, "aid": row[0]},
                )
            except Exception as e:
                logger.warning(
                    "Decrypt failed for agent %s, preserving encrypted value: %s",
                    row[0],
                    e,
                )
    else:
        op.execute(
            "UPDATE agents "
            "SET telegram_token = telegram_token_encrypted "
            "WHERE telegram_token_encrypted != ''"
        )

    # Drop new columns
    op.drop_column("agents", "importance_decay_days")
    op.drop_column("agents", "max_retrieval_results")
    op.drop_column("agents", "embedding_model")
    op.drop_column("agents", "safety_config")
    op.drop_column("agents", "behavior_config")
    op.drop_column("agents", "platform_type")
    op.drop_column("agents", "slack_app_token_encrypted")
    op.drop_column("agents", "slack_bot_token_encrypted")
    op.drop_column("agents", "lark_app_secret_encrypted")
    op.drop_column("agents", "lark_app_id_encrypted")
    op.drop_column("agents", "discord_token_encrypted")
    op.drop_column("agents", "telegram_token_encrypted")
    op.drop_column("agents", "daily_cost_budget_usd")
    op.drop_column("agents", "max_tokens_per_action")
    op.drop_column("agents", "llm_api_key_encrypted")

    # Drop system_settings table
    op.drop_table("system_settings")
