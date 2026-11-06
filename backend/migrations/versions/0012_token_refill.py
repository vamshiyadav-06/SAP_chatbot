"""Token wallet refill date: users.token_refill_at, when the wallet is next topped back up to the allowance
(every TOKEN_REFILL_DAYS days). NULL until the account is first touched; the first touch starts the window.

Additive and idempotent: on an empty database revision 0001 already builds `users` from the current model.

Revision ID: 0012_token_refill
Revises: 0011_token_wallet
Create Date: 2026-11-05
"""
from alembic import op
from sqlalchemy import inspect, text

revision = "0012_token_refill"
down_revision = "0011_token_wallet"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table("users"):
        return
    if "token_refill_at" not in {column["name"] for column in inspector.get_columns("users")}:
        bind.execute(text("ALTER TABLE users ADD COLUMN token_refill_at TIMESTAMP"))


def downgrade() -> None:
    op.get_bind().execute(text("ALTER TABLE users DROP COLUMN IF EXISTS token_refill_at"))
