"""AUDIT_REPORT F-29: Alembic migrations replace the ad-hoc ALTER TABLEs that ran inside init_db.

Uses the *_test database only; the fresh-schema test builds into a private PostgreSQL schema that it drops.
"""

import os
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

from backend.app import database
from backend.app.config import settings
from backend.app.database import SchemaOutOfDateError, engine, init_db, run_migrations, schema_revision_status

EXPECTED_TABLES = {"users", "chats", "messages", "documents", "document_chunks", "citations", "web_sources",
                   "web_images", "uploaded_attachments", "github_repo_chunks", "web_doc_chunks", "shared_prompts"}


def test_init_db_brings_the_test_database_to_the_head_revision():
    init_db()
    current, head = schema_revision_status()
    assert current == head
    assert "source_tier" in {column["name"] for column in inspect(engine).get_columns("documents")}
    # Running again is a no-op.
    run_migrations()
    assert schema_revision_status() == (head, head)


def _empty_database_engine():
    """A database holding only the pgvector extension (no tables), e.g. created with:
    createdb -O sap_brim_ai sap_brim_ai_empty_test && psql -d sap_brim_ai_empty_test -c "CREATE EXTENSION vector"
    In CI the fresh service database plays this role."""
    name = os.getenv("AUDIT_EMPTY_TEST_DATABASE", "sap_brim_ai_empty_test")
    if not name.endswith("_test"):
        pytest.skip("the empty migration database name must end in _test")
    url = make_url(settings.DATABASE_URL).set(database=name)
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg2")
    empty = create_engine(url, connect_args={"connect_timeout": 3})
    try:
        with empty.connect() as conn:
            public_tables = conn.execute(text(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")).scalar_one()
    except OperationalError:
        pytest.skip(f"empty migration database {name} is not available")
    if public_tables:
        pytest.skip(f"{name} is not empty")
    return empty


def test_migrations_build_an_empty_database_and_are_idempotent():
    empty = _empty_database_engine()
    schema = f"audit_migration_{uuid.uuid4().hex}"
    with empty.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        with empty.begin() as conn:
            # pgvector's types live in public (which has no tables); everything is built in the private schema.
            conn.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
            run_migrations(conn)
            run_migrations(conn)
            tables = set(inspect(conn).get_table_names(schema=schema))
            version = conn.execute(text(f'SELECT version_num FROM "{schema}".alembic_version')).scalar_one()
            indexes = {row[0] for row in conn.execute(text(
                "SELECT indexname FROM pg_indexes WHERE schemaname = :schema AND tablename = 'document_chunks'"
            ), {"schema": schema})}
        assert EXPECTED_TABLES <= tables
        assert version == schema_revision_status()[1]
        assert {"ix_document_chunks_embedding_hnsw", "ix_document_chunks_fts"} <= indexes
    finally:
        with empty.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        empty.dispose()


def test_startup_refuses_an_out_of_date_schema_when_auto_migrate_is_off():
    with patch.object(settings, "AUTO_MIGRATE", False), \
            patch.object(database, "schema_revision_status", return_value=("0001_baseline", "9999_future")):
        with pytest.raises(SchemaOutOfDateError):
            init_db()
