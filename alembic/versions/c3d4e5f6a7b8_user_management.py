"""Add users, user_agent_access, and token_usage tables.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-22 00:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False, server_default="user"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "user_agent_access",
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("agent_id", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "agent_id"),
    )
    op.create_index("ix_user_agent_access_user", "user_agent_access", ["user_id"])
    op.create_index("ix_user_agent_access_agent", "user_agent_access", ["agent_id"])

    # Add user_id column to thread_meta for per-user thread isolation
    op.add_column("thread_meta", sa.Column("user_id", sa.String(), nullable=True))
    op.create_index("ix_thread_meta_user_id", "thread_meta", ["user_id"])

    # Token usage tracking
    op.create_table(
        "token_usage",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("agent_id", sa.String(), nullable=False),
        sa.Column("thread_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False, server_default=""),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_token_usage_agent_id", "token_usage", ["agent_id"])
    op.create_index("ix_token_usage_thread_id", "token_usage", ["thread_id"])
    op.create_index("ix_token_usage_user_id", "token_usage", ["user_id"])
    op.create_index("ix_token_usage_agent_thread", "token_usage", ["agent_id", "thread_id"])


def downgrade() -> None:
    op.drop_index("ix_token_usage_agent_thread", table_name="token_usage")
    op.drop_index("ix_token_usage_user_id", table_name="token_usage")
    op.drop_index("ix_token_usage_thread_id", table_name="token_usage")
    op.drop_index("ix_token_usage_agent_id", table_name="token_usage")
    op.drop_table("token_usage")
    op.drop_index("ix_thread_meta_user_id", table_name="thread_meta")
    op.drop_column("thread_meta", "user_id")
    op.drop_index("ix_user_agent_access_agent", table_name="user_agent_access")
    op.drop_index("ix_user_agent_access_user", table_name="user_agent_access")
    op.drop_table("user_agent_access")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
