"""Add expires_at column to api_keys table.

Revision ID: j0e1f2g3h4i5
Revises: i9d0e1f2g3h4
Create Date: 2026-03-25 01:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "j0e1f2g3h4i5"
down_revision = "i9d0e1f2g3h4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("api_keys", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("api_keys", "expires_at")
