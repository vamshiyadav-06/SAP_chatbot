import logging
from typing import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from backend.app.config import settings

logger = logging.getLogger(__name__)

Base = declarative_base()

def get_engine():
    """Attempt connecting to configured PostgreSQL database; fallback to SQLite if unavailable."""
    postgres_url = settings.DATABASE_URL
    try:
        engine = create_engine(postgres_url, pool_pre_ping=True, connect_args={"connect_timeout": 1})
        # Test connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            # Ensure pgvector extension exists if postgres
            try:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.commit()
            except Exception as e:
                logger.warning(f"Could not enable pgvector extension (might not be installed or lacks privileges): {e}")
        logger.info(f"Connected to PostgreSQL database: {postgres_url}")
        return engine
    except Exception as e:
        logger.warning(
            f"Could not connect to PostgreSQL ({postgres_url}): {e}. "
            f"Falling back to local SQLite engine ({settings.SQLITE_FALLBACK_URL})."
        )
        sqlite_engine = create_engine(
            settings.SQLITE_FALLBACK_URL,
            connect_args={"check_same_thread": False}
        )
        return sqlite_engine

engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    from backend.app.models import user, chat, message, document, chunk, citation, web_source  # noqa: F401
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables initialized successfully.")

    if engine.dialect.name == "postgresql":
        try:
            with engine.connect() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                # Create HNSW vector index for high-performance cosine similarity
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding_hnsw "
                    "ON document_chunks USING hnsw (embedding vector_cosine_ops);"
                ))
                # Create GIN full-text search index for high-precision lexical retrieval
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_document_chunks_fts "
                    "ON document_chunks USING gin (to_tsvector('english', chunk_text));"
                ))
                conn.commit()
                logger.info("pgvector HNSW index and GIN full-text search index verified.")
        except Exception as e:
            logger.warning(f"Could not initialize PostgreSQL vector/FTS indices: {e}")

