"""add e2b sandbox columns to agents

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-22 04:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str]] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("sandbox_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "agents",
        sa.Column("e2b_sandbox_id", sa.String(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("agents", "e2b_sandbox_id")
    op.drop_column("agents", "sandbox_enabled")
