"""Answer language: users.preferred_language (Settings), 'en' by default.

Additive and idempotent: on an empty database revision 0001 already builds `users` from the current model.

Revision ID: 0014_user_language
Revises: 0013_user_memories
Create Date: 2026-11-05
"""
from alembic import op
from sqlalchemy import inspect, text

revision = "0014_user_language"
down_revision = "0013_user_memories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table("users"):
        return
    if "preferred_language" not in {column["name"] for column in inspector.get_columns("users")}:
        bind.execute(text("ALTER TABLE users ADD COLUMN preferred_language VARCHAR(8) NOT NULL DEFAULT 'en'"))


def downgrade() -> None:
    op.get_bind().execute(text("ALTER TABLE users DROP COLUMN IF EXISTS preferred_language"))
