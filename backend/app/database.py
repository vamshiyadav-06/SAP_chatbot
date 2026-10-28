import logging
from typing import Generator
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError, OperationalError
from sqlalchemy.orm import Session, sessionmaker, declarative_base
from backend.app.config import settings

logger = logging.getLogger(__name__)

Base = declarative_base()

NUL = "\x00"
NUL_REPLACEMENT = "�"


class DatabaseConnectionError(RuntimeError):
    """PostgreSQL is unreachable or misconfigured. There is no fallback database."""


def describe_target(url: str) -> str:
    """host:port/database without credentials, safe for logs and error messages."""
    try:
        u = make_url(url)
        return f"{u.host}:{u.port or 5432}/{u.database}"
    except ArgumentError:
        return "<unparseable DATABASE_URL>"


def create_db_engine(url: str = None):
    """Creates the PostgreSQL engine. Rejects any non-PostgreSQL URL."""
    url = url or settings.DATABASE_URL
    if not url:
        raise DatabaseConnectionError(
            "DATABASE_URL is not set. Configure it in backend/.env, e.g. "
            "postgresql://sap_brim_ai:<password>@127.0.0.1:5435/sap_brim_ai"
        )
    try:
        parsed = make_url(url)
    except ArgumentError as exc:
        raise DatabaseConnectionError(f"DATABASE_URL is not a valid database URL: {exc}") from exc
    if parsed.get_backend_name() != "postgresql":
        raise DatabaseConnectionError(
            f"DATABASE_URL must point to PostgreSQL + pgvector (got '{parsed.get_backend_name()}'). "
            "PostgreSQL is the only supported database."
        )
    if parsed.drivername == "postgresql":
        # SQLAlchemy 2.1 defaults bare postgresql:// to psycopg 3; this project ships psycopg2.
        parsed = parsed.set(drivername="postgresql+psycopg2")
    return create_engine(
        parsed,
        pool_pre_ping=True,
        pool_size=settings.DATABASE_POOL_SIZE,
        max_overflow=settings.DATABASE_MAX_OVERFLOW,
        pool_recycle=1800,
        connect_args={
            "connect_timeout": settings.DATABASE_CONNECT_TIMEOUT,
            # Naive DateTime columns hold UTC, matching the values written by the app.
            "options": "-c timezone=UTC",
        },
    )


engine = create_db_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@event.listens_for(Session, "before_flush")
def _replace_nul_characters(session, flush_context, instances):
    """PostgreSQL text cannot store NUL (0x00); PDF extraction emits it for unmapped icon glyphs.

    Replaced with U+FFFD, the same rule applied to the three chunks migrated from SQLite.
    Only already-loaded values are inspected, so no lazy loads happen during flush.
    """
    for obj in list(session.new) + list(session.dirty):
        state = inspect(obj)
        for attr in state.mapper.column_attrs:
            value = state.dict.get(attr.key)
            if isinstance(value, str) and NUL in value:
                setattr(obj, attr.key, value.replace(NUL, NUL_REPLACEMENT))
                logger.info("Replaced %d NUL character(s) in %s.%s before writing to PostgreSQL",
                            value.count(NUL), state.mapper.class_.__name__, attr.key)


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_database_connection() -> None:
    """Raises DatabaseConnectionError with an actionable message if PostgreSQL is unreachable."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError as exc:
        raise DatabaseConnectionError(
            f"Cannot connect to PostgreSQL at {describe_target(str(engine.url))}. "
            "Start it with `docker compose up -d postgres` and check DATABASE_URL in backend/.env. "
            f"Driver error: {str(exc.orig).strip()}"
        ) from exc


def create_search_indexes(conn) -> None:
    """pgvector HNSW (cosine) and GIN full-text indexes on document_chunks."""
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding_hnsw "
        "ON document_chunks USING hnsw (embedding vector_cosine_ops)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_document_chunks_fts "
        "ON document_chunks USING gin (to_tsvector('english', chunk_text))"
    ))


def ensure_chat_memory_columns(conn, chat_columns=None) -> None:
    """Apply the existing additive runtime migration convention for chat memory."""
    if chat_columns is None:
        chat_columns = {c["name"] for c in inspect(conn).get_columns("chats")}
    if "summary" not in chat_columns:
        conn.execute(text("ALTER TABLE chats ADD COLUMN summary TEXT"))
    if "summary_through_created_at" not in chat_columns:
        conn.execute(text("ALTER TABLE chats ADD COLUMN summary_through_created_at TIMESTAMP"))
    if "summary_through_message_id" not in chat_columns:
        conn.execute(text("ALTER TABLE chats ADD COLUMN summary_through_message_id VARCHAR(36)"))


def init_db():
    from backend.app.models import user, chat, message, document, chunk, citation, web_source, web_image, uploaded_attachment, repo_chunk, web_doc_chunk, shared_prompt  # noqa: F401
    check_database_connection()

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables initialized successfully on %s.", describe_target(str(engine.url)))

    # Lightweight migrations for databases created before these columns existed.
    # Backfills run only when the column is added, so existing values are never rewritten.
    inspector = inspect(engine)
    user_cols = {c["name"] for c in inspector.get_columns("users")}
    doc_cols = {c["name"] for c in inspector.get_columns("documents")}
    chunk_cols = {c["name"] for c in inspector.get_columns("document_chunks")}
    citation_doc_id = next(c for c in inspector.get_columns("citations") if c["name"] == "document_id")
    chat_cols = {c["name"] for c in inspector.get_columns("chats")}
    message_cols = {c["name"] for c in inspector.get_columns("messages")}
    shared_prompt_cols = {c["name"] for c in inspector.get_columns("shared_prompts")}
    with engine.begin() as conn:
        if "token_version" not in user_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0"))
        ensure_chat_memory_columns(conn, chat_cols)
        if "embedding" not in message_cols:
            conn.execute(text(f"ALTER TABLE messages ADD COLUMN embedding vector({settings.EMBEDDING_DIM})"))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_messages_embedding_hnsw "
            "ON messages USING hnsw (embedding vector_cosine_ops)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_messages_chat_created "
            "ON messages (chat_id, created_at)"
        ))
        if "feedback" not in message_cols:
            conn.execute(text("ALTER TABLE messages ADD COLUMN feedback VARCHAR(10)"))
        if "answer" not in shared_prompt_cols:
            conn.execute(text("ALTER TABLE shared_prompts ADD COLUMN answer TEXT"))
        if "revoked" not in shared_prompt_cols:
            conn.execute(text("ALTER TABLE shared_prompts ADD COLUMN revoked BOOLEAN NOT NULL DEFAULT FALSE"))
        if "role" not in user_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(50) DEFAULT 'consultant'"))
            conn.execute(text("UPDATE users SET role = 'admin' WHERE is_admin = true"))
        document_columns = {
            "file_type": "VARCHAR(50) DEFAULT 'pdf'",
            "file_size_bytes": "INTEGER DEFAULT 0",
            "status": "VARCHAR(50) DEFAULT 'completed'",
            "stage": "VARCHAR(100) DEFAULT 'Indexed'",
            "error_message": "TEXT",
            "vector_indexed": "BOOLEAN DEFAULT true",
            "updated_at": "TIMESTAMP DEFAULT (now() AT TIME ZONE 'utc')",
        }
        for name, ddl in document_columns.items():
            if name not in doc_cols:
                conn.execute(text(f"ALTER TABLE documents ADD COLUMN {name} {ddl}"))
        if "insertion_order" not in chunk_cols:
            conn.execute(text(
                "ALTER TABLE document_chunks ADD COLUMN insertion_order BIGINT GENERATED BY DEFAULT AS IDENTITY"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_document_chunks_insertion_order ON document_chunks (insertion_order)"
            ))
        # Citations store "doc-<filename>" ids (up to 259 chars).
        if getattr(citation_doc_id["type"], "length", None) and citation_doc_id["type"].length < 300:
            conn.execute(text("ALTER TABLE citations ALTER COLUMN document_id TYPE VARCHAR(300)"))
        create_search_indexes(conn)
    logger.info("pgvector HNSW index and GIN full-text search index verified.")

    seed_super_admin()


def seed_super_admin():
    """Create the super admin named in .env. An existing account keeps its password."""
    admin_email = settings.SUPER_ADMIN_EMAIL.strip()
    if not admin_email:
        logger.info("SUPER_ADMIN_EMAIL not set; no super admin account seeded.")
        return
    try:
        from backend.app.models.user import User
        from backend.app.security.auth import hash_password
        with SessionLocal() as db:
            admin_user = db.query(User).filter(User.email == admin_email).first()
            if not admin_user:
                db.add(User(
                    email=admin_email,
                    name="Super Admin",
                    password_hash=hash_password(settings.SUPER_ADMIN_PASSWORD),
                    is_admin=True,
                    role="admin",
                ))
                db.commit()
                logger.info("Super admin account created: %s", admin_email)
            else:
                logger.warning("Configured super admin email already exists; operator must provision admin rights explicitly.")
    except Exception as e:
        logger.warning(f"Could not seed super admin user: {e}")
