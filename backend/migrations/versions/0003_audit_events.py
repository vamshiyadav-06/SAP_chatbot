"""Audit events table (AUDIT_REPORT F-25).

Revision ID: 0003_audit_events
Revises: 0002_access_groups
Create Date: 2026-10-28
"""
from alembic import op
from sqlalchemy import text

revision = "0003_audit_events"
down_revision = "0002_access_groups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(text("""
        CREATE TABLE IF NOT EXISTS audit_events (
            id VARCHAR(36) PRIMARY KEY,
            created_at TIMESTAMP NOT NULL,
            actor_id VARCHAR(36),
            actor_type VARCHAR(20) NOT NULL,
            action VARCHAR(64) NOT NULL,
            target VARCHAR(255),
            ip VARCHAR(64),
            user_agent VARCHAR(300),
            outcome VARCHAR(20) NOT NULL,
            details TEXT
        )
    """))
    op.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_events_created_at ON audit_events (created_at)"))
    op.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_events_action_created ON audit_events (action, created_at)"))
    op.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_events_actor_created ON audit_events (actor_id, created_at)"))


def downgrade() -> None:
    op.execute(text("DROP TABLE IF EXISTS audit_events"))
