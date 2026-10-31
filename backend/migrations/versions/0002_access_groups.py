"""Access groups for users and documents (AUDIT_REPORT F-01).

Every existing user and document gets the group "all", so behaviour is unchanged until an admin
restricts a document to other groups.

Revision ID: 0002_access_groups
Revises: 0001_baseline
Create Date: 2026-10-28
"""
from alembic import op
from sqlalchemy import text

revision = "0002_access_groups"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS groups VARCHAR(100)[] NOT NULL DEFAULT '{all}'"))
    op.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS allowed_groups VARCHAR(100)[] NOT NULL DEFAULT '{all}'"))
    op.execute(text("CREATE INDEX IF NOT EXISTS ix_documents_allowed_groups ON documents USING gin (allowed_groups)"))


def downgrade() -> None:
    op.execute(text("DROP INDEX IF EXISTS ix_documents_allowed_groups"))
    op.execute(text("ALTER TABLE documents DROP COLUMN IF EXISTS allowed_groups"))
    op.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS groups"))
