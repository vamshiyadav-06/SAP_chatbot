import uuid
import numpy as np
from sqlalchemy import BigInteger, Column, ForeignKey, Identity, Integer, String, Text, TypeDecorator
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from backend.app.database import Base
from backend.app.config import settings


class EmbeddingVector(TypeDecorator):
    """pgvector vector(EMBEDDING_DIM) column.

    Results are returned as plain Python lists (not numpy arrays) because callers
    rely on list semantics such as `if emb and len(emb) == dim`.
    """
    impl = Vector
    cache_ok = True

    def __init__(self, dim: int = settings.EMBEDDING_DIM):
        super().__init__(dim)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        # pgvector stores float32 and prints the shortest decimal per component; parsing that
        # straight to float64 yields a nearby value. Widening through float32 returns exactly
        # the stored values (identical to the float32-derived floats the embedder produced).
        return np.asarray(value, dtype=np.float32).astype(np.float64).tolist()

class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    document_name = Column(String(255), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    page_number = Column(Integer, nullable=False)
    section = Column(String(255), nullable=True)
    chunk_text = Column(Text, nullable=False)
    metadata_json = Column(Text, nullable=True)
    embedding = Column(EmbeddingVector, nullable=False)
    # Monotonic insertion sequence (carried over from the SQLite rowid). Retrieval loads
    # chunks in this order so rank ties break exactly as they did before the migration.
    insertion_order = Column(BigInteger, Identity(always=False), nullable=False, index=True)

    document = relationship("Document", back_populates="chunks")
