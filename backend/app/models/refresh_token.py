"""Refresh tokens (Alembic revision 0010_refresh_tokens).

The browser holds the raw token in an HttpOnly cookie; only its SHA-256 hash is stored here. Every sign-in
starts a new family; each refresh rotates the token inside its family (the old row is marked rotated and
points at its replacement). A rotated token presented again after the grace window revokes the whole
family (theft detection). `token_version` is the user's token_version at issue, so a password change,
logout, reset or deactivation also ends every refresh token. Deleting the user removes their rows
(ON DELETE CASCADE). Timestamps are naive UTC, like every TIMESTAMP column in this schema.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from backend.app.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    family_id = Column(String(36), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True)
    token_version = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=_now)
    expires_at = Column(DateTime, nullable=False)
    rotated_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    replaced_by_id = Column(String(36), nullable=True)
