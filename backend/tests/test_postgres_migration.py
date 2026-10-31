"""
Regression tests for the SQLite -> PostgreSQL + pgvector cutover.

Runs against the "_test" database (see conftest.py). Tests that compare with the
original SQLite data use the newest backup in backups/sqlite/ (read-only) and are
skipped when no backup is present. No embeddings are generated for stored chunks.
"""

import json
import random
import re
import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from backend.app import database, main
from backend.app.config import settings
from backend.app.database import (
    DatabaseConnectionError,
    SessionLocal,
    check_database_connection,
    create_db_engine,
    engine,
    get_db,
)
from backend.app.models.chunk import DocumentChunk
from backend.app.models.document import Document
from backend.app.models.user import User
from backend.app.security.auth import create_access_token

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
BACKUPS = sorted((ROOT_DIR / "backups" / "sqlite").glob("sap_assistant_*.db"))
UNREACHABLE_URL = "postgresql://nobody:nothing@127.0.0.1:1/unreachable"

requires_backup = pytest.mark.skipif(not BACKUPS, reason="no SQLite migration backup present")


def _backup_connection():
    return sqlite3.connect(f"file:{BACKUPS[-1].as_posix()}?mode=ro", uri=True)


def _float32_vector(seed: int):
    rng = np.random.default_rng(seed)
    return rng.standard_normal(settings.EMBEDDING_DIM).astype(np.float32).astype(np.float64).tolist()


@pytest.fixture
def temp_document():
    """A throwaway document with two chunks; removed afterwards even if the test fails."""
    doc_id = str(uuid.uuid4())
    db = SessionLocal()
    try:
        db.add(Document(id=doc_id, filename=f"pytest-migration-{doc_id}.pdf", title="pytest migration",
                        file_hash="0" * 64, page_count=1))
        db.add_all([
            DocumentChunk(document_id=doc_id, document_name="pytest-migration.pdf", chunk_index=i,
                          page_number=1, section="Page 1", chunk_text=f"pytest chunk {i}\x00icon",
                          embedding=_float32_vector(i))
            for i in range(2)
        ])
        db.commit()
        yield doc_id
    finally:
        db.rollback()
        db.query(Document).filter(Document.id == doc_id).delete()
        db.commit()
        db.close()


# ----------------------------------------------------------------- PostgreSQL only, no fallback

def test_engine_is_postgresql_test_database():
    assert engine.dialect.name == "postgresql"
    assert engine.url.database.endswith("_test")


@pytest.mark.parametrize("url", ["sqlite:///backend/sap_assistant.db", "mysql://u:p@localhost/db"])
def test_non_postgresql_urls_are_rejected(url):
    with pytest.raises(DatabaseConnectionError, match="PostgreSQL"):
        create_db_engine(url)


def test_missing_database_url_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "DATABASE_URL", "")
    with pytest.raises(DatabaseConnectionError, match="DATABASE_URL is not set"):
        create_db_engine()


def test_application_code_has_no_sqlite_usage():
    # Provenance comments may mention SQLite; any actual use of it may not.
    usage = re.compile(r"import sqlite3|sqlite3\.|sqlite\+?\w*://|SQLITE_|dialect\.name\s*==\s*['\"]sqlite|aiosqlite",
                       re.IGNORECASE)
    app_dir = ROOT_DIR / "backend" / "app"
    offenders = [str(p.relative_to(ROOT_DIR)) for p in app_dir.rglob("*.py")
                 if usage.search(p.read_text(encoding="utf-8"))]
    assert offenders == []
    assert "sqlite" not in (ROOT_DIR / "backend" / "requirements.txt").read_text().lower()


def test_unreachable_database_raises_clear_error(monkeypatch):
    monkeypatch.setattr(database, "engine", create_db_engine(UNREACHABLE_URL))
    with pytest.raises(DatabaseConnectionError, match=r"Cannot connect to PostgreSQL at 127\.0\.0\.1:1/unreachable"):
        check_database_connection()


def test_startup_fails_without_database(monkeypatch):
    monkeypatch.setattr(database, "engine", create_db_engine(UNREACHABLE_URL))
    with pytest.raises(DatabaseConnectionError):
        with TestClient(main.app):
            pass


def test_health_reports_503_when_database_down(monkeypatch):
    monkeypatch.setattr(main, "SessionLocal", sessionmaker(bind=create_db_engine(UNREACHABLE_URL)))
    response = TestClient(main.app).get("/health")
    assert response.status_code == 503
    assert response.json()["database"]["status"] == "unavailable"


def test_api_reports_503_when_database_down():
    bad_sessions = sessionmaker(bind=create_db_engine(UNREACHABLE_URL))

    def broken_db():
        db = bad_sessions()
        try:
            yield db
        finally:
            db.close()

    main.app.dependency_overrides[get_db] = broken_db
    try:
        token = create_access_token({"sub": str(uuid.uuid4())})
        response = TestClient(main.app).get("/api/chats", headers={"Authorization": f"Bearer {token}"})
    finally:
        main.app.dependency_overrides.pop(get_db, None)
    assert response.status_code == 503
    assert "Database unavailable" in response.json()["detail"]


# ----------------------------------------------------------------- schema and vector storage

def test_embedding_columns_are_pgvector_384():
    with engine.connect() as conn:
        types = dict(conn.execute(text(
            "SELECT c.relname, format_type(a.atttypid, a.atttypmod) FROM pg_attribute a "
            "JOIN pg_class c ON c.oid = a.attrelid WHERE a.attname = 'embedding' AND c.relkind = 'r'"
        )).fetchall())
        indexes = {r[0] for r in conn.execute(text(
            "SELECT indexname FROM pg_indexes WHERE tablename = 'document_chunks'"))}
    assert types == {t: f"vector({settings.EMBEDDING_DIM})"
                     for t in ("document_chunks", "github_repo_chunks", "web_doc_chunks", "messages")}
    assert {"ix_document_chunks_embedding_hnsw", "ix_document_chunks_fts"} <= indexes


def test_vector_roundtrip_is_exact_and_returned_as_list(temp_document):
    db = SessionLocal()
    try:
        chunks = (db.query(DocumentChunk).filter(DocumentChunk.document_id == temp_document)
                  .order_by(DocumentChunk.chunk_index).all())
        assert [type(c.embedding) for c in chunks] == [list, list]
        assert [c.embedding for c in chunks] == [_float32_vector(0), _float32_vector(1)]
    finally:
        db.close()


def test_nul_characters_are_replaced_before_write(temp_document):
    with engine.connect() as conn:
        texts = conn.execute(text("SELECT chunk_text FROM document_chunks WHERE document_id = :d"),
                             {"d": temp_document}).scalars().all()
    assert sorted(texts) == ["pytest chunk 0�icon", "pytest chunk 1�icon"]


def test_new_chunks_continue_insertion_order(temp_document):
    with engine.connect() as conn:
        new_orders = conn.execute(text(
            "SELECT insertion_order FROM document_chunks WHERE document_id = :d ORDER BY chunk_index"),
            {"d": temp_document}).scalars().all()
        older_max = conn.execute(text(
            "SELECT MAX(insertion_order) FROM document_chunks WHERE document_id <> :d"),
            {"d": temp_document}).scalar()
    assert new_orders[0] > older_max and new_orders[1] > new_orders[0]


def test_document_delete_removes_chunks_and_vectors(temp_document):
    db = SessionLocal()
    try:
        db.delete(db.get(Document, temp_document))
        db.commit()
        assert db.query(DocumentChunk).filter(DocumentChunk.document_id == temp_document).count() == 0
    finally:
        db.close()


def test_document_ingest_retrieve_and_delete_via_api(monkeypatch, tmp_path):
    """Upload -> process (embeds only this new document) -> retrievable -> API delete purges vectors."""
    from backend.app.services.document_processing_service import document_processing_service
    from backend.app.services.retrieval_service import retrieval_service

    monkeypatch.setattr(settings, "DOCUMENTS_DIR", tmp_path)  # keep knowledge_base/documents untouched
    client = TestClient(main.app)
    headers = {"X-Admin-Key": settings.ADMIN_API_KEY}
    term = f"PGMIGR{uuid.uuid4().hex[:8].upper()}"
    content = f"Convergent invoicing migration check. Unique identifier {term} appears in this document."
    upload = client.post("/api/documents/upload", headers=headers,
                         files=[("files", (f"pg_migration_{term}.txt", content.encode("utf-8"), "text/plain"))])
    assert upload.status_code == 201, upload.text
    doc_id = upload.json()["documents"][0]["id"]
    try:
        with SessionLocal() as db:
            document_processing_service._execute_pipeline(db, document_ids=[doc_id], force=True)
        with engine.connect() as conn:
            dims = conn.execute(text("SELECT vector_dims(embedding) FROM document_chunks WHERE document_id = :d"),
                                {"d": doc_id}).scalars().all()
        assert dims and set(dims) == {settings.EMBEDDING_DIM}

        with SessionLocal() as db:  # Self-authored uploads stay out of evidence until classified.
            uploaded = db.query(Document).filter(Document.id == doc_id).one()
            assert uploaded.source_tier == "self_authored"
            assert not any(r["document_id"] == doc_id for r in retrieval_service.hybrid_search(db, term, top_k=5))
            uploaded.source_tier = "official_sap"
            db.commit()
            retrieval_service.invalidate_cache()
            assert any(r["document_id"] == doc_id for r in retrieval_service.hybrid_search(db, term, top_k=5))

        deleted = client.delete(f"/api/documents/{doc_id}", headers=headers)
        assert deleted.status_code == 200, deleted.text
        assert deleted.json()["deleted_chunks"] == len(dims)
        with engine.connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM document_chunks WHERE document_id = :d"),
                                {"d": doc_id}).scalar() == 0
        with SessionLocal() as db:
            assert not any(r["document_id"] == doc_id for r in retrieval_service.hybrid_search(db, term, top_k=5))
    finally:
        with SessionLocal() as db:
            db.query(Document).filter(Document.id == doc_id).delete()
            db.commit()


def test_pgvector_nearest_neighbour_on_stored_vectors():
    with engine.connect() as conn:
        chunk_id = conn.execute(text("SELECT id FROM document_chunks ORDER BY insertion_order LIMIT 1")).scalar()
        top = conn.execute(text(
            "SELECT id, embedding <=> (SELECT embedding FROM document_chunks WHERE id = :id) AS dist "
            "FROM document_chunks ORDER BY dist LIMIT 1"), {"id": chunk_id}).one()
    assert top.dist == pytest.approx(0.0, abs=1e-6)


def test_concurrent_sessions_read_and_write():
    emails = [f"pytest-concurrency-{uuid.uuid4()}@example.com" for _ in range(24)]

    def read_task(_):
        with SessionLocal() as db:
            count = db.query(DocumentChunk).count()
            db.execute(text("SELECT id FROM document_chunks ORDER BY embedding <=> "
                            "(SELECT embedding FROM document_chunks LIMIT 1) LIMIT 5")).fetchall()
            return count

    def write_task(email):
        with SessionLocal() as db:
            db.add(User(email=email, name="pytest", password_hash="x"))
            db.commit()
            return email

    try:
        with ThreadPoolExecutor(max_workers=24) as pool:
            counts = list(pool.map(read_task, range(48)))
            list(pool.map(write_task, emails))
        assert len(set(counts)) == 1 and counts[0] > 0
        with SessionLocal() as db:
            assert db.query(User).filter(User.email.in_(emails)).count() == len(emails)
    finally:
        with SessionLocal() as db:
            db.query(User).filter(User.email.in_(emails)).delete(synchronize_session=False)
            db.commit()


# ----------------------------------------------------------------- preservation vs. SQLite backup

@requires_backup
def test_migrated_vectors_match_sqlite_backup_exactly():
    src = _backup_connection()
    rows = src.execute("SELECT id, embedding, rowid FROM document_chunks").fetchall()
    sample = random.Random(7).sample(rows, 300)
    with engine.connect() as conn:
        stored = {r.id: r for r in conn.execute(text(
            "SELECT id, embedding::text AS emb, insertion_order FROM document_chunks WHERE id = ANY(:ids)"),
            {"ids": [r[0] for r in sample]})}
    assert len(stored) == len(sample)
    for chunk_id, raw, rowid in sample:
        expected = np.asarray(json.loads(raw), dtype=np.float64)
        actual = np.array(stored[chunk_id].emb.strip("[]").split(","), dtype=np.float32).astype(np.float64)
        assert np.array_equal(actual, expected), chunk_id
        assert stored[chunk_id].insertion_order == rowid
    # Through the ORM the application sees exactly the floats SQLite held.
    with SessionLocal() as db:
        for chunk_id, raw, _ in sample[:25]:
            assert db.get(DocumentChunk, chunk_id).embedding == json.loads(raw), chunk_id


class _FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def count(self):
        return len(self.rows)

    def order_by(self, *_):
        return self

    def all(self):
        return self.rows


class _FakeDB:
    def __init__(self, rows):
        self.rows = rows

    def query(self, _model):
        return _FakeQuery(self.rows)


@requires_backup
def test_hybrid_search_matches_pre_migration_sqlite_results():
    from backend.app.services.retrieval_service import RetrievalService

    src = _backup_connection()
    sqlite_rows = [
        SimpleNamespace(id=r[0], document_id=r[1], document_name=r[2], page_number=r[3], section=r[4],
                        chunk_text=r[5], embedding=json.loads(r[6]))
        for r in src.execute("SELECT id, document_id, document_name, page_number, section, chunk_text, "
                             "embedding FROM document_chunks ORDER BY rowid")
    ]
    with SessionLocal() as db:
        # Only migrated chunks: other tests may add documents to the test database.
        pg_rows = (db.query(DocumentChunk)
                   .filter(DocumentChunk.id.in_([r.id for r in sqlite_rows]))
                   .order_by(DocumentChunk.insertion_order).all())
        db.expunge_all()

    questions = [
        "How are billable items transferred to convergent invoicing in SAP BRIM?",
        "Explain the FI-CA clearing control and account balance clearing with FPL9.",
        "How is payment lot processing done with FP05?",
        "How to configure billable item classes in SPRO?",
        "What is a provider contract in SAP BRIM and how is it created from subscription order management?",
    ]
    before, after = RetrievalService(), RetrievalService()
    for question in questions:
        expected = before.hybrid_search(_FakeDB(sqlite_rows), question, top_k=10)
        actual = after.hybrid_search(_FakeDB(pg_rows), question, top_k=10)
        assert [r["chunk_id"] for r in actual] == [r["chunk_id"] for r in expected], question
        assert [r["score"] for r in actual] == [r["score"] for r in expected], question
