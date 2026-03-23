"""Replace sandbox_enabled boolean with sandbox_mode string column.

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-03-24 01:00:00.000000+00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "g7b8c9d0e1f2"
down_revision: Union[str, Sequence[str]] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new sandbox_mode column with default "base"
    op.add_column(
        "agents",
        sa.Column("sandbox_mode", sa.String(), nullable=False, server_default="base"),
    )
    # Migrate existing data: sandbox_enabled=true -> "base", false -> "none"
    op.execute(
        "UPDATE agents SET sandbox_mode = CASE "
        "WHEN sandbox_enabled = true THEN 'base' "
        "ELSE 'none' END"
    )
    # Drop old column
    op.drop_column("agents", "sandbox_enabled")


def downgrade() -> None:
    # Add back sandbox_enabled
    op.add_column(
        "agents",
        sa.Column("sandbox_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    # Migrate data back: "none" -> false, anything else -> true
    op.execute(
        "UPDATE agents SET sandbox_enabled = CASE "
        "WHEN sandbox_mode = 'none' THEN false "
        "ELSE true END"
    )
    op.drop_column("agents", "sandbox_mode")
