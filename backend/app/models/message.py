import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Float, DateTime, ForeignKey, Index, event
from sqlalchemy.orm import relationship
from backend.app.database import Base
from backend.app.models.chunk import EmbeddingVector
from backend.app.config import settings

class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_chat_created", "chat_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    chat_id = Column(String(36), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(50), nullable=False)  # 'user', 'assistant'
    content = Column(Text, nullable=False)
    source_type = Column(String(50), nullable=True)  # 'knowledge_base', 'web', 'refusal', 'error', 'conversation_memory'
    grounding_score = Column(Float, nullable=True)
    feedback = Column(String(10), nullable=True)  # 'up', 'down' or NULL; assistant answers only
    embedding = Column(EmbeddingVector, nullable=True)
    embedding_model = Column(String(255), nullable=False, default=settings.EMBEDDING_MODEL, server_default="legacy-unknown")
    embedding_version = Column(String(64), nullable=False, default=settings.EMBEDDING_VERSION, server_default="legacy-unknown")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    chat = relationship("Chat", back_populates="messages")
    citations = relationship("Citation", back_populates="message", cascade="all, delete-orphan")
    web_sources = relationship("WebSource", back_populates="message", cascade="all, delete-orphan")
    images = relationship("WebImage", back_populates="message", cascade="all, delete-orphan")
    uploaded_attachments = relationship("UploadedAttachment", back_populates="message", cascade="all, delete-orphan")


@event.listens_for(Message, "before_insert")
@event.listens_for(Message, "before_update")
def set_embedding_provenance(_mapper, _connection, message):
    if message.embedding is not None:
        message.embedding_model = settings.EMBEDDING_MODEL
        message.embedding_version = settings.EMBEDDING_VERSION
