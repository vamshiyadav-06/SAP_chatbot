import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, Boolean, Text, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship
from backend.app.database import Base

class Document(Base):
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    filename = Column(String(255), unique=True, index=True, nullable=False)
    title = Column(String(255), nullable=False)
    file_hash = Column(String(64), index=True, nullable=False)
    version = Column(String(50), default="1.0", nullable=False)
    page_count = Column(Integer, default=0, nullable=False)
    file_type = Column(String(50), default="pdf", nullable=False)
    file_size_bytes = Column(Integer, default=0, nullable=False)
    source_tier = Column(String(50), default="self_authored", server_default=text("'self_authored'"), nullable=False)
    status = Column(String(50), default="completed", index=True, nullable=False)  # pending, processing, completed, failed
    stage = Column(String(100), default="Indexed", nullable=False)
    error_message = Column(Text, nullable=True)
    vector_indexed = Column(Boolean, default=True, nullable=False)
    # Groups whose members may retrieve this document (AUDIT_REPORT F-01); "all" keeps it visible to everyone.
    allowed_groups = Column(ARRAY(String(100)), nullable=False, default=lambda: ["all"], server_default=text("'{all}'"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")

