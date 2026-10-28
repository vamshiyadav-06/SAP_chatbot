"""
One-time SQLite -> PostgreSQL + pgvector migration utility.

PostgreSQL is the application's only database. This utility is retained for
recovery and auditability of the original cutover; normal operation never
reads SQLite.

Subcommands
-----------
backup   Consistent online backup (sqlite3 backup API, includes committed WAL
         pages) plus a manifest of tables, row counts, IDs and vector counts.
migrate  Copies every table into PostgreSQL inside ONE transaction, in batches,
         with ON CONFLICT (id) DO NOTHING duplicate protection. Existing
         embeddings are copied verbatim - the embedding model is never called.
verify   Compares every row and column of the source with the target,
         including exact float32 equality of every vector component.

Usage (from the repository root)
--------------------------------
    python backend/scripts/migrate_sqlite_to_pgvector.py backup  --source backend/sap_assistant.db
    python backend/scripts/migrate_sqlite_to_pgvector.py migrate --source backups/sqlite/<backup>.db
    python backend/scripts/migrate_sqlite_to_pgvector.py verify  --source backups/sqlite/<backup>.db

The target defaults to DATABASE_URL from backend/.env; override with --target-url.

Conversion policy (anything outside it aborts the migration):
- BOOLEAN 0/1 -> boolean; DATETIME text -> timestamp (microseconds preserved,
  timezone-aware values are rejected).
- Embeddings: JSON text -> vector(EMBEDDING_DIM). Every component must already
  be exactly representable as float32 (pgvector's storage type), so the copy is
  lossless; wrong dimensions or non-finite values abort.
- PostgreSQL text cannot contain NUL (0x00). NUL characters are replaced with
  U+FFFD (approved for the original cutover); every replacement is logged with
  the original value JSON-escaped, and the SQLite backup keeps the original.
- VARCHAR values longer than the target column abort (no truncation).
"""

import argparse
import hashlib
import json
import logging
import math
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, select, text  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402

from backend.app.config import settings  # noqa: E402
from backend.app.database import Base, create_db_engine, create_search_indexes  # noqa: E402
from backend.app.models import *  # noqa: E402,F401,F403  (registers every table on Base.metadata)
from backend.app.models.chunk import EmbeddingVector  # noqa: E402

DEFAULT_BACKUP_DIR = ROOT_DIR / "backups" / "sqlite"
DEFAULT_LOG_DIR = ROOT_DIR / "backups" / "migration_logs"
BATCH_SIZE = 500
NUL = "\x00"
NUL_REPLACEMENT = "�"

# Parent tables first so foreign keys are satisfied inside the single transaction.
TABLE_ORDER = [
    "users",
    "documents",
    "chats",
    "document_chunks",
    "messages",
    "citations",
    "web_sources",
    "web_images",
    "uploaded_attachments",
    "github_repo_chunks",
    "web_doc_chunks",
]
VECTOR_TABLES = ["document_chunks", "github_repo_chunks", "web_doc_chunks"]
# The implicit SQLite rowid (insertion order) is preserved in these identity columns;
# retrieval loads chunks in this order, so rank ties break exactly as before.
ROWID_COLUMNS = {"document_chunks": "insertion_order"}

logger = logging.getLogger("sqlite_to_pgvector")


class MigrationError(RuntimeError):
    """Raised when a value cannot be preserved exactly; the migration aborts."""


# --------------------------------------------------------------------------- helpers

def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _setup_logging(log_dir: Path, action: str) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{action}_{_timestamp()}.log"
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(fmt)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(fmt)
    logger.handlers[:] = [file_handler, stream_handler]
    logger.setLevel(logging.INFO)
    return log_path


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _open_sqlite_readonly(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise FileNotFoundError(f"SQLite source not found: {path}")
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)


def _sqlite_tables(conn: sqlite3.Connection) -> List[str]:
    return [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )]


def _target_url(args) -> str:
    url = args.target_url or settings.DATABASE_URL
    if not url.startswith("postgresql"):
        raise MigrationError(f"Target must be a PostgreSQL URL, got: {url.split('@')[-1]}")
    return url


def _redact(url: str) -> str:
    return url.split("@")[-1]


def _parse_vector(raw: Any, row_id: str, table: str) -> List[float]:
    if raw is None:
        return None
    try:
        values = json.loads(raw) if isinstance(raw, str) else list(raw)
    except Exception as exc:
        raise MigrationError(f"{table}.{row_id}: embedding is not valid JSON ({exc})")
    if len(values) != settings.EMBEDDING_DIM:
        raise MigrationError(
            f"{table}.{row_id}: embedding has {len(values)} dims, expected {settings.EMBEDDING_DIM}"
        )
    arr = np.asarray(values, dtype=np.float64)
    if not np.all(np.isfinite(arr)):
        raise MigrationError(f"{table}.{row_id}: embedding contains non-finite values")
    if np.any(arr.astype(np.float32).astype(np.float64) != arr):
        raise MigrationError(
            f"{table}.{row_id}: embedding has values not exactly representable as float32; "
            f"pgvector storage would round them"
        )
    return [float(v) for v in values]


def _convert_value(table: str, column, raw: Any, row_id: str, nul_log: List[Dict[str, Any]]) -> Any:
    """Converts one SQLite value to the exact Python value written to PostgreSQL."""
    if raw is None:
        return None
    col_type = column.type
    if isinstance(col_type, EmbeddingVector):
        return _parse_vector(raw, row_id, table)
    if isinstance(col_type, Boolean):
        if raw not in (0, 1, True, False):
            raise MigrationError(f"{table}.{row_id}.{column.name}: invalid boolean {raw!r}")
        return bool(raw)
    if isinstance(col_type, DateTime):
        dt = datetime.fromisoformat(raw) if isinstance(raw, str) else raw
        if dt.tzinfo is not None:
            raise MigrationError(f"{table}.{row_id}.{column.name}: timezone-aware value {raw!r}")
        return dt
    if isinstance(col_type, Integer):
        if isinstance(raw, float) and not raw.is_integer():
            raise MigrationError(f"{table}.{row_id}.{column.name}: non-integer {raw!r}")
        return int(raw)
    if isinstance(col_type, Float):
        value = float(raw)
        if not math.isfinite(value):
            raise MigrationError(f"{table}.{row_id}.{column.name}: non-finite float {raw!r}")
        return value
    if isinstance(col_type, (String, Text)):
        value = raw if isinstance(raw, str) else str(raw)
        if NUL in value:
            nul_log.append({
                "table": table,
                "id": row_id,
                "column": column.name,
                "nul_count": value.count(NUL),
                "original_json": json.dumps(value),
            })
            value = value.replace(NUL, NUL_REPLACEMENT)
        length = getattr(col_type, "length", None)
        if length is not None and len(value) > length:
            raise MigrationError(
                f"{table}.{row_id}.{column.name}: value length {len(value)} exceeds VARCHAR({length})"
            )
        return value
    return raw


def _read_source_rows(conn: sqlite3.Connection, table_name: str, nul_log: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Returns converted rows; aborts if SQLite has columns the model does not know."""
    table = Base.metadata.tables[table_name]
    source_cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{table_name}")')]
    unknown = set(source_cols) - set(table.columns.keys())
    if unknown:
        raise MigrationError(f"{table_name}: source columns {sorted(unknown)} have no target column")
    cols = [c for c in table.columns if c.name in source_cols]
    quoted = [f'"{c.name}"' for c in cols]
    rowid_col = ROWID_COLUMNS.get(table_name)
    if rowid_col:
        cols.append(table.columns[rowid_col])
        quoted.append("rowid")
    rows = []
    for raw_row in conn.execute(f'SELECT {", ".join(quoted)} FROM "{table_name}" ORDER BY "id"'):
        row_id = raw_row[[c.name for c in cols].index("id")]
        rows.append({
            c.name: _convert_value(table_name, c, raw, row_id, nul_log)
            for c, raw in zip(cols, raw_row)
        })
    return rows


def _id_digest(ids: List[str]) -> str:
    return hashlib.sha256("\n".join(sorted(ids)).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- backup

def cmd_backup(args) -> int:
    source = Path(args.source).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    _setup_logging(DEFAULT_LOG_DIR, "backup")

    stamp = _timestamp()
    backup_path = out_dir / f"sap_assistant_{stamp}.db"
    logger.info("Backing up %s -> %s", source, backup_path)

    src = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    dst = sqlite3.connect(backup_path)
    with dst:
        src.backup(dst)  # page-level consistent snapshot, includes committed WAL frames
    dst.close()
    src.close()

    check = sqlite3.connect(f"file:{backup_path.as_posix()}?mode=ro", uri=True)
    integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        logger.error("Backup integrity_check failed: %s", integrity)
        return 1

    manifest: Dict[str, Any] = {
        "created_utc": stamp,
        "source_path": str(source),
        "source_sha256": _sha256_file(source),
        "backup_path": str(backup_path),
        "backup_sha256": _sha256_file(backup_path),
        "integrity_check": integrity,
        "journal_mode": check.execute("PRAGMA journal_mode").fetchone()[0],
        "tables": {},
    }
    for table in _sqlite_tables(check):
        ids = [r[0] for r in check.execute(f'SELECT "id" FROM "{table}"')]
        entry: Dict[str, Any] = {"row_count": len(ids), "id_sha256": _id_digest(ids)}
        if table in VECTOR_TABLES:
            entry["vector_count"] = check.execute(
                f'SELECT COUNT(*) FROM "{table}" WHERE embedding IS NOT NULL'
            ).fetchone()[0]
        if table in ("documents", "document_chunks"):
            entry["ids"] = sorted(ids)
        manifest["tables"][table] = entry
        logger.info("  %-22s rows=%-6d %s", table, len(ids),
                    f"vectors={entry['vector_count']}" if "vector_count" in entry else "")
    check.close()

    manifest_path = backup_path.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    logger.info("Backup OK (sha256 %s). Manifest: %s", manifest["backup_sha256"], manifest_path)
    return 0


# --------------------------------------------------------------------------- migrate

def cmd_migrate(args) -> int:
    source = Path(args.source).resolve()
    target_url = _target_url(args)
    log_path = _setup_logging(DEFAULT_LOG_DIR, "migrate")
    logger.info("Source (read-only): %s", source)
    logger.info("Target: %s", _redact(target_url))

    src = _open_sqlite_readonly(source)
    extra = set(_sqlite_tables(src)) - set(TABLE_ORDER)
    if extra:
        logger.error("Source has tables with no migration mapping: %s", sorted(extra))
        return 1

    engine = create_db_engine(target_url)
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.create_all(bind=engine)

    with engine.connect() as conn:
        non_empty = {
            t: conn.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar()
            for t in TABLE_ORDER
        }
    non_empty = {t: n for t, n in non_empty.items() if n}
    if non_empty and not args.allow_existing:
        logger.error("Target tables already contain rows: %s. Re-run with --allow-existing to "
                     "insert only missing IDs (existing rows are never overwritten).", non_empty)
        return 1

    nul_log: List[Dict[str, Any]] = []
    report: Dict[str, Any] = {"source": str(source), "target": _redact(target_url),
                              "started_utc": _timestamp(), "tables": {}}
    try:
        with engine.begin() as conn:  # single transaction: all tables or nothing
            for table_name in TABLE_ORDER:
                table = Base.metadata.tables[table_name]
                if table_name not in _sqlite_tables(src):
                    logger.info("%-22s absent in source, skipped", table_name)
                    continue
                rows = _read_source_rows(src, table_name, nul_log)
                inserted = 0
                for start in range(0, len(rows), BATCH_SIZE):
                    batch = rows[start:start + BATCH_SIZE]
                    stmt = pg_insert(table).on_conflict_do_nothing(index_elements=["id"])
                    result = conn.execute(stmt, batch)
                    inserted += max(result.rowcount, 0)
                skipped = len(rows) - inserted
                rowid_col = ROWID_COLUMNS.get(table_name)
                if rowid_col:
                    # Identity columns accept explicit values; continue new inserts after the max.
                    conn.execute(text(
                        f"SELECT setval(pg_get_serial_sequence('{table_name}', '{rowid_col}'), "
                        f"COALESCE((SELECT MAX({rowid_col}) FROM {table_name}), 0) + 1, false)"
                    ))
                report["tables"][table_name] = {"source_rows": len(rows), "inserted": inserted,
                                                "skipped_existing": skipped}
                logger.info("%-22s source=%-6d inserted=%-6d skipped_existing=%d",
                            table_name, len(rows), inserted, skipped)
            for item in nul_log:
                logger.warning("NUL replaced with U+FFFD: %s.%s id=%s count=%d original=%s",
                               item["table"], item["column"], item["id"], item["nul_count"],
                               item["original_json"])
            create_search_indexes(conn)
    except MigrationError as exc:
        logger.error("ABORTED, transaction rolled back, nothing written: %s", exc)
        return 1

    report["nul_replacements"] = nul_log
    report["finished_utc"] = _timestamp()
    report_path = log_path.with_suffix(".json")
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info("Migration committed. Report: %s", report_path)
    logger.info("Next: run the 'verify' subcommand before using the database.")
    return 0


# --------------------------------------------------------------------------- verify

def _normalize(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    return value


def _vectors_equal(expected: Optional[List[float]], actual_text: Optional[str]) -> Tuple[bool, float]:
    if expected is None or actual_text is None:
        return expected is None and actual_text is None, 0.0
    # pgvector prints the shortest decimal that round-trips each float32 component.
    actual = np.array(actual_text.strip("[]").split(","), dtype=np.float32).astype(np.float64)
    exp = np.asarray(expected, dtype=np.float64)
    if actual.shape != exp.shape:
        return False, float("inf")
    diff = float(np.max(np.abs(actual - exp))) if exp.size else 0.0
    return bool(np.array_equal(actual, exp)), diff


def cmd_verify(args) -> int:
    source = Path(args.source).resolve()
    target_url = _target_url(args)
    log_path = _setup_logging(DEFAULT_LOG_DIR, "verify")
    logger.info("Verifying %s against %s", source, _redact(target_url))

    src = _open_sqlite_readonly(source)
    engine = create_db_engine(target_url)
    source_tables = set(_sqlite_tables(src))
    failures: List[str] = []
    report: Dict[str, Any] = {"source": str(source), "target": _redact(target_url), "tables": {}}
    nul_log: List[Dict[str, Any]] = []

    with engine.connect() as conn:
        for table_name in TABLE_ORDER:
            if table_name not in source_tables:
                continue
            table = Base.metadata.tables[table_name]
            expected_rows = {r["id"]: r for r in _read_source_rows(src, table_name, nul_log)}
            vector_cols = [c.name for c in table.columns if isinstance(c.type, EmbeddingVector)]
            plain_cols = [c for c in table.columns if c.name not in vector_cols]
            select_cols = list(plain_cols) + [text(f'"{v}"::text AS "{v}"') for v in vector_cols]
            actual_rows = {r._mapping["id"]: dict(r._mapping)
                           for r in conn.execute(select(*select_cols).select_from(table))}

            missing = sorted(set(expected_rows) - set(actual_rows))
            extra = sorted(set(actual_rows) - set(expected_rows))
            value_mismatches: List[Dict[str, Any]] = []
            vectors_checked = vectors_exact = 0
            max_vector_diff = 0.0
            for row_id in sorted(set(expected_rows) & set(actual_rows)):
                exp, act = expected_rows[row_id], actual_rows[row_id]
                for col in plain_cols:
                    if col.name not in exp:
                        continue
                    if _normalize(exp[col.name]) != _normalize(act[col.name]):
                        value_mismatches.append({"id": row_id, "column": col.name})
                for vcol in vector_cols:
                    if vcol not in exp:
                        continue
                    equal, diff = _vectors_equal(exp[vcol], act[vcol])
                    if exp[vcol] is not None:
                        vectors_checked += 1
                        vectors_exact += int(equal)
                        max_vector_diff = max(max_vector_diff, diff)
                    if not equal:
                        value_mismatches.append({"id": row_id, "column": vcol, "max_abs_diff": diff})

            entry = {
                "source_rows": len(expected_rows),
                "target_rows": len(actual_rows),
                "missing_in_target": missing[:20],
                "missing_count": len(missing),
                "extra_in_target": extra[:20],
                "extra_count": len(extra),
                "value_mismatches": value_mismatches[:20],
                "value_mismatch_count": len(value_mismatches),
            }
            if vector_cols:
                entry.update({"vectors_checked": vectors_checked, "vectors_exact": vectors_exact,
                              "max_abs_vector_diff": max_vector_diff})
            report["tables"][table_name] = entry
            ok = not missing and not extra and not value_mismatches
            if not ok:
                failures.append(table_name)
            logger.info("%-22s %s source=%-6d target=%-6d missing=%d extra=%d mismatches=%d%s",
                        table_name, "OK  " if ok else "FAIL", len(expected_rows), len(actual_rows),
                        len(missing), len(extra), len(value_mismatches),
                        f" vectors_exact={vectors_exact}/{vectors_checked} max_diff={max_vector_diff}"
                        if vector_cols else "")

        # Schema checks: vector column types, foreign keys, orphans.
        dims = conn.execute(text(
            "SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod) "
            "FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid "
            "WHERE a.attname = 'embedding' AND c.relkind = 'r' AND a.attnum > 0"
        )).fetchall()
        report["vector_columns"] = {r[0]: r[2] for r in dims}
        for rel, _, typ in dims:
            if typ != f"vector({settings.EMBEDDING_DIM})":
                failures.append(f"{rel}.embedding type {typ}")
        stored_dims = conn.execute(text(
            "SELECT vector_dims(embedding), COUNT(*) FROM document_chunks GROUP BY 1"
        )).fetchall()
        report["document_chunk_dims"] = {str(d): n for d, n in stored_dims}

        fks = conn.execute(text(
            "SELECT conrelid::regclass::text, confrelid::regclass::text, confdeltype "
            "FROM pg_constraint WHERE contype = 'f' ORDER BY 1"
        )).fetchall()
        report["foreign_keys"] = [{"table": r[0], "references": r[1], "on_delete": r[2]} for r in fks]
        expected_fks = {("chats", "users"), ("document_chunks", "documents"), ("messages", "chats"),
                        ("citations", "messages"), ("web_sources", "messages"),
                        ("web_images", "messages"), ("uploaded_attachments", "messages")}
        present = {(r[0], r[1]) for r in fks if r[2] == "c"}
        for fk in sorted(expected_fks - present):
            failures.append(f"missing ON DELETE CASCADE FK {fk[0]} -> {fk[1]}")

        orphan_chunks = conn.execute(text(
            "SELECT COUNT(*) FROM document_chunks c LEFT JOIN documents d ON d.id = c.document_id "
            "WHERE d.id IS NULL")).scalar()
        report["orphan_document_chunks"] = orphan_chunks
        if orphan_chunks:
            failures.append(f"{orphan_chunks} orphan document_chunks")

        # Deletion + vector cleanup, executed inside a transaction that is rolled back.
        doc_id = conn.execute(text(
            "SELECT document_id FROM document_chunks GROUP BY document_id ORDER BY COUNT(*) LIMIT 1"
        )).scalar()
        if doc_id:
            before = conn.execute(text("SELECT COUNT(*) FROM document_chunks WHERE document_id = :d"),
                                  {"d": doc_id}).scalar()
            conn.rollback()
            trans = conn.begin()
            conn.execute(text("DELETE FROM documents WHERE id = :d"), {"d": doc_id})
            after = conn.execute(text("SELECT COUNT(*) FROM document_chunks WHERE document_id = :d"),
                                 {"d": doc_id}).scalar()
            trans.rollback()
            restored = conn.execute(text("SELECT COUNT(*) FROM document_chunks WHERE document_id = :d"),
                                    {"d": doc_id}).scalar()
            report["delete_cascade_check"] = {"document_id": doc_id, "chunks_before": before,
                                              "chunks_after_delete": after,
                                              "chunks_after_rollback": restored}
            if after != 0 or restored != before:
                failures.append("document delete did not cascade to chunks/vectors")
            logger.info("Delete cascade check (rolled back): %d chunks -> %d after delete -> %d after rollback",
                        before, after, restored)

    report["expected_nul_replacements"] = [
        {k: v for k, v in item.items() if k != "original_json"} for item in nul_log
    ]
    report["failures"] = failures
    report_path = log_path.with_suffix(".json")
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    if failures:
        logger.error("VERIFICATION FAILED: %s. Report: %s", failures, report_path)
        return 1
    logger.info("VERIFICATION PASSED: all rows, columns and vectors match. Report: %s", report_path)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_backup = sub.add_parser("backup", help="Consistent SQLite backup + manifest")
    p_backup.add_argument("--source", required=True)
    p_backup.add_argument("--out-dir", default=str(DEFAULT_BACKUP_DIR))
    p_backup.set_defaults(func=cmd_backup)

    for name, func, help_text in (("migrate", cmd_migrate, "Copy SQLite rows into PostgreSQL"),
                                  ("verify", cmd_verify, "Compare SQLite source with PostgreSQL")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--source", required=True, help="SQLite file (use the backup, not the live file)")
        p.add_argument("--target-url", default=None, help="PostgreSQL URL (default: DATABASE_URL)")
        if name == "migrate":
            p.add_argument("--allow-existing", action="store_true",
                           help="Target may already hold rows; only missing IDs are inserted")
        p.set_defaults(func=func)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
