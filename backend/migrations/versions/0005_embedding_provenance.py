"""Track the model used to create stored embeddings (AUDIT_REPORT F-07).

Revision ID: 0005_embedding_provenance
Revises: 0004_document_source_tier
Create Date: 2026-10-29
"""
from alembic import op
from sqlalchemy import inspect, text

revision = "0005_embedding_provenance"
down_revision = "0004_document_source_tier"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    for table in ("document_chunks", "messages"):
        if not inspector.has_table(table):
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        if "embedding_model" not in columns:
            bind.execute(text(
                f"ALTER TABLE {table} ADD COLUMN embedding_model VARCHAR(255) "
                "NOT NULL DEFAULT 'legacy-unknown'"
            ))
        if "embedding_version" not in columns:
            bind.execute(text(
                f"ALTER TABLE {table} ADD COLUMN embedding_version VARCHAR(64) "
                "NOT NULL DEFAULT 'legacy-unknown'"
            ))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    for table in ("document_chunks", "messages"):
        if not inspector.has_table(table):
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        for column in ("embedding_version", "embedding_model"):
            if column in columns:
                bind.execute(text(f"ALTER TABLE {table} DROP COLUMN {column}"))
