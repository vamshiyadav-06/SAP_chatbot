import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, Boolean

from backend.app.database import Base


class SharedPrompt(Base):
    """Public, read-only snapshot of one user prompt, reachable by an unguessable token."""

    __tablename__ = "shared_prompts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    token = Column(String(32), unique=True, nullable=False, index=True, default=lambda: secrets.token_urlsafe(16))
    # One link per prompt: sharing again refreshes the snapshot instead of minting a new link.
    message_id = Column(String(36), ForeignKey("messages.id", ondelete="CASCADE"), unique=True, nullable=False)
    content = Column(Text, nullable=False)
    # Set when an answer was shared: message_id is then the answer and content its question.
    answer = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)
