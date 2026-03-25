"""Add contacts table for contact directory.

Revision ID: k1f2g3h4i5j6
Revises: j0e1f2g3h4i5
Create Date: 2026-03-25 03:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "k1f2g3h4i5j6"
down_revision = "j0e1f2g3h4i5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contacts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("platform", sa.String(), nullable=False),
        sa.Column("platform_id", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("source", sa.String(), nullable=False, server_default="auto"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_contacts_platform_id", "contacts", ["platform", "platform_id"], unique=True)
    op.create_index("ix_contacts_display_name", "contacts", ["display_name"])


def downgrade() -> None:
    op.drop_index("ix_contacts_display_name", table_name="contacts")
    op.drop_index("ix_contacts_platform_id", table_name="contacts")
    op.drop_table("contacts")
