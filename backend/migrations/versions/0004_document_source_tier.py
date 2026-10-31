"""Persist document authority tiers with a conservative default (AUDIT_REPORT F-53).

Revision ID: 0004_document_source_tier
Revises: 0003_audit_events
Create Date: 2026-10-29
"""
from alembic import op
from sqlalchemy import inspect, text

revision = "0004_document_source_tier"
down_revision = "0003_audit_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("documents")}
    added_column = "source_tier" not in columns
    if added_column:
        bind.execute(text(
            "ALTER TABLE documents ADD COLUMN source_tier VARCHAR(50) "
            "NOT NULL DEFAULT 'self_authored'"
        ))

    # Preserve known classifications from the reviewed historical filename map.
    # Any unmapped document remains at the least-authoritative tier.
    if not added_column:
        return

    from backend.app.corpus.tier_definitions import DOCUMENT_TIER_MAPPING

    for filename, metadata in DOCUMENT_TIER_MAPPING.items():
        tier = metadata.get("tier")
        if tier:
            bind.execute(text(
                "UPDATE documents SET source_tier = :tier "
                "WHERE filename = :filename AND source_tier = 'self_authored'"
            ), {"filename": filename, "tier": tier})


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("documents")}
    if "source_tier" in columns:
        bind.execute(text("ALTER TABLE documents DROP COLUMN source_tier"))
