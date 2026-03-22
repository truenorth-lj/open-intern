"""add delivery_platform and delivery_chat_id to scheduled_jobs

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-03-22 06:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str]] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scheduled_jobs",
        sa.Column("delivery_platform", sa.String(), nullable=False, server_default=""),
    )
    op.add_column(
        "scheduled_jobs",
        sa.Column("delivery_chat_id", sa.String(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("scheduled_jobs", "delivery_chat_id")
    op.drop_column("scheduled_jobs", "delivery_platform")
