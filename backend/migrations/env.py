"""Alembic environment. Uses the application's engine settings; never reads a URL from alembic.ini."""

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.database import Base, create_db_engine  # noqa: E402
import backend.app.models  # noqa: E402,F401  (registers every table on Base.metadata)

# Only one process migrates at a time (several API workers may start together).
MIGRATION_LOCK_ID = 727274001

config = context.config
target_metadata = Base.metadata


def run_with_connection(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        connection.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": MIGRATION_LOCK_ID})
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:  # called from init_db with the application's connection
        run_with_connection(connection)
        return
    if config.config_file_name:
        fileConfig(config.config_file_name, disable_existing_loggers=False)
    engine = create_db_engine()
    with engine.connect() as connection:
        run_with_connection(connection)
        connection.commit()


if context.is_offline_mode():
    raise RuntimeError("Offline (SQL script) migrations are not supported; run against a database.")
run_migrations_online()
