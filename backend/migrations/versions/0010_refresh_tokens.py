"""Refresh tokens: rotated, hashed, family-revocable sessions behind an HttpOnly cookie.

Adds `refresh_tokens` (see backend/app/models/refresh_token.py). Only the SHA-256 hash of each token is
stored. Deleting a user removes their tokens (ON DELETE CASCADE).

Additive and idempotent (IF NOT EXISTS), like every migration after 0001.

Revision ID: 0010_refresh_tokens
Revises: 0009_projects
Create Date: 2026-11-04
"""
from alembic import op
from sqlalchemy import text

revision = "0010_refresh_tokens"
down_revision = "0009_projects"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(text("""
        CREATE TABLE IF NOT EXISTS refresh_tokens (
            id VARCHAR(36) PRIMARY KEY,
            user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            family_id VARCHAR(36) NOT NULL,
            token_hash VARCHAR(64) NOT NULL UNIQUE,
            token_version INTEGER NOT NULL,
            created_at TIMESTAMP NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            rotated_at TIMESTAMP,
            revoked_at TIMESTAMP,
            replaced_by_id VARCHAR(36)
        )
    """))
    bind.execute(text("CREATE INDEX IF NOT EXISTS ix_refresh_tokens_user_id ON refresh_tokens (user_id)"))
    bind.execute(text("CREATE INDEX IF NOT EXISTS ix_refresh_tokens_family_id ON refresh_tokens (family_id)"))


def downgrade() -> None:
    op.get_bind().execute(text("DROP TABLE IF EXISTS refresh_tokens"))
