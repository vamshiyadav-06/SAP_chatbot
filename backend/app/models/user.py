import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, Integer, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship
from backend.app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    role = Column(String(50), default="consultant", nullable=False)
    token_version = Column(Integer, default=0, nullable=False)
    # Access groups (AUDIT_REPORT F-01): retrieval only uses documents sharing one of these groups.
    groups = Column(ARRAY(String(100)), nullable=False, default=lambda: ["all"], server_default=text("'{all}'"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    chats = relationship("Chat", back_populates="user", cascade="all, delete-orphan")
