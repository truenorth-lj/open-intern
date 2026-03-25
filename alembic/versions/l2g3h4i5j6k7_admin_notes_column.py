"""Add admin_notes column to agents table.

Revision ID: l2g3h4i5j6k7
Revises: k1f2g3h4i5j6
Create Date: 2026-03-25 12:55:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "l2g3h4i5j6k7"
down_revision = "k1f2g3h4i5j6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("admin_notes", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("agents", "admin_notes")
