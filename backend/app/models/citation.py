import uuid
from sqlalchemy import Column, String, Integer, Float, Text, ForeignKey
from sqlalchemy.orm import relationship
from backend.app.database import Base

class Citation(Base):
    __tablename__ = "citations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    message_id = Column(String(36), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type = Column(String(50), default="knowledge_base", nullable=False)
    document_id = Column(String(300), nullable=False)  # "doc-" + document filename (<= 255)
    document_name = Column(String(255), nullable=False)
    chunk_id = Column(String(36), nullable=False)
    page_number = Column(Integer, nullable=False)
    section = Column(String(255), nullable=True)
    similarity_score = Column(Float, nullable=False)
    citation_text = Column(Text, nullable=False)

    message = relationship("Message", back_populates="citations")
