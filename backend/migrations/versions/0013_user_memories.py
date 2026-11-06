"""Permanent user memory: the user_memories table (things a user asked the assistant to remember).

Additive and idempotent: on an empty database revision 0001 already builds it from the current model.

Revision ID: 0013_user_memories
Revises: 0012_token_refill
Create Date: 2026-11-05
"""
from alembic import op
from sqlalchemy import text

revision = "0013_user_memories"
down_revision = "0012_token_refill"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(text("""
        CREATE TABLE IF NOT EXISTS user_memories (
            id VARCHAR(36) PRIMARY KEY,
            user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            content TEXT NOT NULL,
            source_chat_id VARCHAR(36),
            created_at TIMESTAMP NOT NULL
        )
    """))
    bind.execute(text("CREATE INDEX IF NOT EXISTS ix_user_memories_user_id ON user_memories (user_id)"))


def downgrade() -> None:
    op.get_bind().execute(text("DROP TABLE IF EXISTS user_memories"))
