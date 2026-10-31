import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Index, String, Text

from backend.app.database import Base


class AuditEvent(Base):
    """Security-relevant actions: who did what, to what, from where, and the outcome (AUDIT_REPORT F-25)."""

    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_created_at", "created_at"),
        Index("ix_audit_events_action_created", "action", "created_at"),
        Index("ix_audit_events_actor_created", "actor_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    actor_id = Column(String(36), nullable=True)  # user id; null for anonymous callers and the admin key
    actor_type = Column(String(20), nullable=False)  # user | admin | admin_key | anonymous | system
    action = Column(String(64), nullable=False)
    target = Column(String(255), nullable=True)
    ip = Column(String(64), nullable=True)
    user_agent = Column(String(300), nullable=True)
    outcome = Column(String(20), nullable=False)  # success | failure | denied
    details = Column(Text, nullable=True)  # JSON; never passwords, tokens or message content
