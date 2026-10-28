"""
Test database isolation.

Many tests create users, chats and documents through SessionLocal, so the suite must
never run against the live database. Tests use "<DATABASE_URL database>_test" on the
same PostgreSQL server (or TEST_DATABASE_URL when set). Create it as a clone of the
live database, which also gives retrieval tests the real indexed knowledge base:

    docker exec sap_assistant_postgres createdb -U sap_assistant -O sap_brim_ai -T sap_brim_ai sap_brim_ai_test

This module runs before any test module imports backend.app.database, so the engine
is bound to the test database from the start.
"""

import os

from sqlalchemy.engine import make_url

from backend.app.config import settings


def _resolve_test_database_url() -> str:
    explicit = os.getenv("TEST_DATABASE_URL")
    if explicit:
        return explicit
    if not settings.DATABASE_URL:
        return ""
    url = make_url(settings.DATABASE_URL)
    if url.database.endswith("_test"):
        return settings.DATABASE_URL
    return url.set(database=f"{url.database}_test").render_as_string(hide_password=False)


TEST_DATABASE_URL = _resolve_test_database_url()
if TEST_DATABASE_URL:
    if not make_url(TEST_DATABASE_URL).database.endswith("_test"):
        raise RuntimeError(
            "Refusing to run tests against a database whose name does not end in '_test' "
            f"({make_url(TEST_DATABASE_URL).database}). Tests write data."
        )
    settings.DATABASE_URL = TEST_DATABASE_URL
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
