"""Add tsvector and pgvector columns for hybrid search.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-03-23 17:00:00.000000+00:00
"""

from alembic import op

# revision identifiers
revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension (idempotent)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Add tsvector column for BM25 full-text search
    op.execute(
        "ALTER TABLE memories ADD COLUMN IF NOT EXISTS "
        "content_tsv tsvector GENERATED ALWAYS AS "
        "(to_tsvector('english', content)) STORED"
    )

    # Add GIN index for full-text search
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_memories_content_tsv ON memories USING GIN (content_tsv)"
    )

    # Add pgvector embedding column (1536 dimensions for text-embedding-3-small)
    op.execute("ALTER TABLE memories ADD COLUMN IF NOT EXISTS content_embedding vector(1536)")

    # Add HNSW index for approximate nearest neighbor search
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_memories_content_embedding "
        "ON memories USING hnsw (content_embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_memories_content_embedding")
    op.execute("ALTER TABLE memories DROP COLUMN IF EXISTS content_embedding")
    op.execute("DROP INDEX IF EXISTS ix_memories_content_tsv")
    op.execute("ALTER TABLE memories DROP COLUMN IF EXISTS content_tsv")
