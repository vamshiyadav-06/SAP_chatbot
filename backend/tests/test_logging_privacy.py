"""Every log record passes the privacy filter, wherever it is emitted.

``PrivacyLogFilter`` used to sit only on the root console handler: uvicorn's own handlers (propagate=False)
printed unhandled-exception tracebacks unredacted, and the quiet third-party loggers (propagate=False, no
handler) fell through to ``logging.lastResort`` unfiltered. Also covers bcrypt/password_hash redaction,
SQL errors without bound parameters, the Scholar audit line without the question text, and the super
admin e-mail being stored the way login looks it up.
"""
import io
import logging
from unittest.mock import MagicMock

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from backend.app.logging_config import UVICORN_LOGGERS, VERBOSE_LOGGERS, setup_logging
from backend.app.security.log_safety import PrivacyLogFilter, privacy_fingerprint, redact_log_text

EMAIL = "jane.doe@example.com"
BCRYPT = "$2b$12$" + "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0"  # 7 + 53 characters


def _is_pytest_handler(handler):
    return type(handler).__module__.startswith("_pytest")


@pytest.fixture
def restore_logging():
    """setup_logging() rewires global loggers; put the session's configuration back afterwards (pytest's
    own capture handlers on the root are left to pytest)."""
    names = ["", *VERBOSE_LOGGERS, *UVICORN_LOGGERS]
    saved = {}
    for name in names:
        lg = logging.getLogger(name)
        handlers = [h for h in lg.handlers if not _is_pytest_handler(h)]
        saved[name] = (handlers, list(lg.filters), lg.level, lg.propagate)
    last_resort = list(logging.lastResort.filters)
    yield
    for name, (handlers, filters, level, propagate) in saved.items():
        lg = logging.getLogger(name)
        lg.handlers[:] = [h for h in lg.handlers if _is_pytest_handler(h)] + handlers
        lg.filters[:] = filters
        lg.setLevel(level)
        lg.propagate = propagate
    logging.lastResort.filters[:] = last_resort


def _stream_handler(stream, formatter=None):
    handler = logging.StreamHandler(stream)
    handler.setFormatter(formatter or logging.Formatter("%(name)s %(message)s"))
    return handler


def _root_console_stream():
    stream = io.StringIO()
    for handler in logging.getLogger().handlers:
        if not _is_pytest_handler(handler):
            handler.setStream(stream)
    return stream


def _log_unhandled_exception():
    try:
        raise RuntimeError(f"login failed for {EMAIL} password_hash={BCRYPT}")
    except RuntimeError:
        logging.getLogger("uvicorn.error").exception("Exception in ASGI application")


# --- redaction rules -----------------------------------------------------------------------------------

def test_bcrypt_hashes_are_redacted_wherever_they_appear():
    for prefix in ("$2a$", "$2b$", "$2y$"):
        value = prefix + BCRYPT[4:]
        out = redact_log_text(f"row ('admin', '{value}') failed")
        assert value not in out and "[REDACTED_HASH]" in out


def test_password_hash_values_are_redacted():
    for line in (
        "password_hash=s3cr3t-value-here",
        "[parameters: {'password_hash': 'plain-or-hash-value', 'email': 'x'}]",
        'password_hash: "another-value"',
    ):
        out = redact_log_text(line)
        assert "s3cr3t-value-here" not in out
        assert "plain-or-hash-value" not in out
        assert "another-value" not in out
        assert "password_hash" in out


# --- every handler path is filtered ------------------------------------------------------------------

@pytest.mark.parametrize("uvicorn_configures_after_app_import", [False, True])
def test_uvicorn_error_tracebacks_are_redacted(restore_logging, uvicorn_configures_after_app_import):
    stream = io.StringIO()
    uvicorn_logger = logging.getLogger("uvicorn")
    if not uvicorn_configures_after_app_import:
        # `uvicorn backend.app.main:app`: uvicorn's dictConfig runs before the app module is imported.
        uvicorn_logger.handlers[:] = [_stream_handler(stream)]
        uvicorn_logger.propagate = False
        setup_logging("INFO")
    else:
        # `uvicorn.run(app)` / reload workers: uvicorn replaces its handlers after setup_logging ran.
        setup_logging("INFO")
        uvicorn_logger.handlers[:] = [_stream_handler(stream)]
        uvicorn_logger.propagate = False

    _log_unhandled_exception()

    out = stream.getvalue()
    assert "Exception in ASGI application" in out and "RuntimeError" in out
    assert EMAIL not in out and BCRYPT not in out
    assert "[REDACTED_EMAIL]" in out


def test_setup_logging_attaches_the_filter_to_existing_uvicorn_handlers(restore_logging):
    handler = _stream_handler(io.StringIO())
    logging.getLogger("uvicorn").handlers[:] = [handler]
    setup_logging("INFO")
    assert any(isinstance(f, PrivacyLogFilter) for f in handler.filters)
    setup_logging("INFO")  # re-initialisation does not stack filters
    assert sum(isinstance(f, PrivacyLogFilter) for f in handler.filters) == 1


def test_uvicorn_access_lines_are_redacted_and_still_formatted(restore_logging):
    from uvicorn.logging import AccessFormatter

    stream = io.StringIO()
    access = logging.getLogger("uvicorn.access")
    access.handlers[:] = [_stream_handler(stream, AccessFormatter('%(client_addr)s "%(request_line)s" %(status_code)s', use_colors=False))]
    access.propagate = False
    setup_logging("INFO")
    access.setLevel(logging.INFO)

    access.info('%s - "%s %s HTTP/%s" %d', "10.0.0.1:5000", "GET", f"/api/x?email={EMAIL}", "1.1", 200)

    out = stream.getvalue()
    assert "GET /api/x?email=[REDACTED_EMAIL] HTTP/1.1" in out and "200" in out
    assert EMAIL not in out


@pytest.mark.parametrize("name", ["httpx", "sqlalchemy.engine", "asyncio"])
def test_quiet_third_party_warnings_reach_the_filtered_root_handler(restore_logging, capsys, name):
    setup_logging("INFO")
    stream = _root_console_stream()

    logging.getLogger(name).warning("request for %s failed", EMAIL)
    logging.getLogger(name).info("chatty %s", EMAIL)

    out = stream.getvalue()
    assert "request for [REDACTED_EMAIL] failed" in out
    assert "chatty" not in out  # still quiet below WARNING
    assert EMAIL not in capsys.readouterr().err  # not printed unfiltered by logging.lastResort


def test_last_resort_handler_is_filtered(restore_logging, capsys):
    setup_logging("INFO")
    orphan = logging.getLogger("test_logging_privacy.orphan")
    orphan.propagate = False  # no handler anywhere: logging.lastResort prints it
    try:
        orphan.warning("orphan record for %s", EMAIL)
    finally:
        orphan.propagate = True
    err = capsys.readouterr().err
    assert "orphan record for [REDACTED_EMAIL]" in err and EMAIL not in err


# --- SQL errors, the Scholar audit line, the super admin seed ------------------------------------------

def test_sql_errors_never_include_bound_parameters():
    from backend.app import database

    engine = database.create_db_engine()
    try:
        assert engine.hide_parameters is True
        with engine.connect() as conn:
            # A runtime error PostgreSQL reports without echoing the statement, so any bound value in the
            # message could only come from SQLAlchemy's "[parameters: ...]" section.
            with pytest.raises(DBAPIError) as error:
                conn.execute(
                    text("SELECT CAST(:value AS text), 1 / CAST(:zero AS integer)"),
                    {"value": f"{EMAIL} {BCRYPT}", "zero": 0},
                )
        assert "division by zero" in str(error.value)
        assert EMAIL not in str(error.value) and BCRYPT not in str(error.value)
        assert "hide_parameters" in str(error.value)
    finally:
        engine.dispose()


def test_scholar_audit_line_logs_a_fingerprint_not_the_question(caplog):
    from backend.app.services.confidence_scoring import log_report

    question = "How does ACME Corp bill customer 4711 in SAP BRIM?"
    with caplog.at_level(logging.INFO, logger="backend.app.services.confidence_scoring"):
        log_report({"decision": "publish", "overall_confidence": 0.8, "components": {}}, question)

    assert "ACME" not in caplog.text and "How does" not in caplog.text
    assert f"query_hash={privacy_fingerprint(question)}" in caplog.text
    assert f"query_length={len(question)}" in caplog.text


def test_super_admin_email_is_stored_lower_case(monkeypatch):
    from backend.app import database
    from backend.app.config import settings

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    factory = MagicMock()
    factory.return_value.__enter__.return_value = db
    monkeypatch.setattr(database, "SessionLocal", factory)
    monkeypatch.setattr(settings, "SUPER_ADMIN_EMAIL", "  Owner.Admin@Example.COM ")
    monkeypatch.setattr(settings, "SUPER_ADMIN_PASSWORD", "Seeded-Password-123")

    database.seed_super_admin()

    created = db.add.call_args.args[0]
    assert created.email == "owner.admin@example.com"
    lookup = db.query.return_value.filter.call_args.args[0]
    assert lookup.right.value == "owner.admin@example.com"
