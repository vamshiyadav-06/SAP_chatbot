"""Privacy helpers for application logs."""

import hashlib
import logging
import re


_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_LONG_DIGITS = re.compile(r"\b\d{7,}\b")


def privacy_fingerprint(value: str) -> str:
    """Return a stable short reference without logging the supplied text/name."""
    return hashlib.sha256((value or "").encode("utf-8", errors="replace")).hexdigest()[:12]


def redact_log_text(value: str) -> str:
    value = _EMAIL.sub("[REDACTED_EMAIL]", value or "")
    return _LONG_DIGITS.sub("[REDACTED_DIGITS]", value)


class PrivacyLogFilter(logging.Filter):
    """Redact common PII in messages and exception tracebacks before handlers emit records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_log_text(record.getMessage())
        record.args = ()
        if record.exc_info:
            record.exc_text = redact_log_text(logging.Formatter().formatException(record.exc_info))
            record.exc_info = None
        return True
