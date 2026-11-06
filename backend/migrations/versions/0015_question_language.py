"""Question language: users.question_language (Settings); NULL means the same as the answer language.

Additive and idempotent: on an empty database revision 0001 already builds `users` from the current model.

Revision ID: 0015_question_language
Revises: 0014_user_language
Create Date: 2026-11-06
"""
from alembic import op
from sqlalchemy import inspect, text

revision = "0015_question_language"
down_revision = "0014_user_language"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table("users"):
        return
    if "question_language" not in {column["name"] for column in inspector.get_columns("users")}:
        bind.execute(text("ALTER TABLE users ADD COLUMN question_language VARCHAR(8)"))


def downgrade() -> None:
    op.get_bind().execute(text("ALTER TABLE users DROP COLUMN IF EXISTS question_language"))
