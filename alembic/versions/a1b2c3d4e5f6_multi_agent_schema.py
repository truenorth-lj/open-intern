"""multi-agent schema: agents table, agent_id columns

Revision ID: a1b2c3d4e5f6
Revises: 6b6009bdebb2
Create Date: 2026-03-22 03:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str]] = "6b6009bdebb2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- agents table ---
    op.create_table(
        "agents",
        sa.Column("agent_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False, server_default="AI Employee"),
        sa.Column(
            "personality",
            sa.Text(),
            nullable=False,
            server_default="You are a helpful AI employee.",
        ),
        sa.Column("avatar_url", sa.String(), nullable=False, server_default=""),
        sa.Column("llm_provider", sa.String(), nullable=False, server_default="claude"),
        sa.Column("llm_model", sa.String(), nullable=False, server_default="claude-sonnet-4-6"),
        sa.Column("llm_temperature", sa.Float(), nullable=False, server_default="0.7"),
        sa.Column("telegram_token", sa.String(), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("agent_id"),
        if_not_exists=True,
    )

    # --- Add agent_id to memories ---
    op.add_column(
        "memories",
        sa.Column("agent_id", sa.String(), nullable=False, server_default="default"),
    )
    op.create_index("ix_memories_agent_id", "memories", ["agent_id"], if_not_exists=True)
    op.create_index(
        "ix_memories_agent_scope",
        "memories",
        ["agent_id", "scope"],
        if_not_exists=True,
    )

    # --- Add agent_id to thread_meta ---
    op.add_column(
        "thread_meta",
        sa.Column("agent_id", sa.String(), nullable=False, server_default="default"),
    )
    op.create_index("ix_thread_meta_agent_id", "thread_meta", ["agent_id"], if_not_exists=True)


def downgrade() -> None:
    op.drop_index("ix_thread_meta_agent_id", table_name="thread_meta")
    op.drop_column("thread_meta", "agent_id")
    op.drop_index("ix_memories_agent_scope", table_name="memories")
    op.drop_index("ix_memories_agent_id", table_name="memories")
    op.drop_column("memories", "agent_id")
    op.drop_table("agents")
