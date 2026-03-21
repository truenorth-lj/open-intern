"""add scheduled_jobs table

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-22 04:16:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str]] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scheduled_jobs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("agent_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("schedule_type", sa.String(), nullable=False),
        sa.Column("schedule_expr", sa.String(), nullable=False),
        sa.Column("timezone", sa.String(), nullable=False, server_default="UTC"),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("channel_id", sa.String(), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_status", sa.String(), nullable=True),
        sa.Column("last_run_error", sa.Text(), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scheduled_jobs_agent_id", "scheduled_jobs", ["agent_id"])
    op.create_index("ix_scheduled_jobs_enabled", "scheduled_jobs", ["enabled"])


def downgrade() -> None:
    op.drop_index("ix_scheduled_jobs_enabled")
    op.drop_index("ix_scheduled_jobs_agent_id")
    op.drop_table("scheduled_jobs")
