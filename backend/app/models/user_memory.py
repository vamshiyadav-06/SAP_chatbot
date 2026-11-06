"""Permanent per-user memory (Alembic revision 0013_user_memories): things a user asked the assistant to
remember ("save it"). Private to the user, used in every chat of that user, deleted with the account."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Text

from backend.app.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class UserMemory(Base):
    __tablename__ = "user_memories"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    source_chat_id = Column(String(36), nullable=True)
    created_at = Column(DateTime, default=_now, nullable=False)
