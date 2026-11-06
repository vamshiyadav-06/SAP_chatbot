"""Free token wallet: users.token_balance_milli (thousandths of a token), 1,000 tokens for every account.

Additive and idempotent: on an empty database revision 0001 already builds `users` from the current model.
Existing accounts receive the 1,000 free tokens once, through the column default.

Revision ID: 0011_token_wallet
Revises: 0010_refresh_tokens
Create Date: 2026-11-05
"""
from alembic import op
from sqlalchemy import inspect, text

revision = "0011_token_wallet"
down_revision = "0010_refresh_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table("users"):
        return
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "token_balance_milli" not in columns:
        bind.execute(text("ALTER TABLE users ADD COLUMN token_balance_milli INTEGER NOT NULL DEFAULT 1000000"))


def downgrade() -> None:
    op.get_bind().execute(text("ALTER TABLE users DROP COLUMN IF EXISTS token_balance_milli"))
