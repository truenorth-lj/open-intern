"""Add SSH backend columns to agents table.

Revision ID: i9d0e1f2g3h4
Revises: h8c9d0e1f2g3
Create Date: 2026-03-24 12:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "i9d0e1f2g3h4"
down_revision = "h8c9d0e1f2g3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("ssh_host", sa.String(), nullable=False, server_default=""))
    op.add_column(
        "agents", sa.Column("ssh_port", sa.Integer(), nullable=False, server_default=sa.text("22"))
    )
    op.add_column(
        "agents", sa.Column("ssh_user", sa.String(), nullable=False, server_default="user")
    )
    op.add_column(
        "agents", sa.Column("ssh_key_encrypted", sa.Text(), nullable=False, server_default="")
    )


def downgrade() -> None:
    op.drop_column("agents", "ssh_key_encrypted")
    op.drop_column("agents", "ssh_user")
    op.drop_column("agents", "ssh_port")
    op.drop_column("agents", "ssh_host")
