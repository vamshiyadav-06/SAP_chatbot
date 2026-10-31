import uuid

from sqlalchemy import inspect, text

from backend.app.database import engine, ensure_chat_memory_columns


def test_chat_memory_additive_migration_preserves_existing_data():
    """Exercise the runtime migration against a private legacy-shaped schema."""
    schema = f"codex_memory_migration_{uuid.uuid4().hex}"
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        with engine.begin() as conn:
            conn.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            conn.execute(text("CREATE TABLE chats (id VARCHAR(36) PRIMARY KEY, title VARCHAR(255) NOT NULL)"))
            conn.execute(text("INSERT INTO chats (id, title) VALUES ('legacy-chat', 'Existing chat')"))
            before = {col["name"] for col in inspect(conn).get_columns("chats")}
            ensure_chat_memory_columns(conn, before)

            # The second application is idempotent and does not replace data.
            after_first = {col["name"] for col in inspect(conn).get_columns("chats")}
            ensure_chat_memory_columns(conn, after_first)
            after_second = {col["name"] for col in inspect(conn).get_columns("chats")}
            row = conn.execute(text("SELECT id, title, summary FROM chats WHERE id = 'legacy-chat'")).one()

        assert {"summary", "summary_through_created_at", "summary_through_message_id"} <= after_first
        assert after_first == after_second
        assert row.id == "legacy-chat"
        assert row.title == "Existing chat"
        assert row.summary is None
    finally:
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
