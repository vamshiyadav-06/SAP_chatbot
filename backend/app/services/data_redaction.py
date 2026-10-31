"""Small, replaceable PII redaction hook for outbound text prompts."""

import re
from typing import Dict, Tuple


_PATTERNS = (
    ("email", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE), "[REDACTED_EMAIL]"),
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?\b", re.IGNORECASE), "[REDACTED_IBAN]"),
    ("phone", re.compile(r"(?<!\w)(?:\+\d[\d .()/-]{7,}\d|\d{3}[ .-]\d{3}[ .-]\d{4})(?!\w)"), "[REDACTED_PHONE]"),
    ("sap_account_number", re.compile(r"(?<!\d)\d{10}(?!\d)"), "[REDACTED_SAP_ACCOUNT]"),
)


def redact_external_text(value: str) -> Tuple[str, Dict[str, int]]:
    """Redact common identifiers before text is sent to a third-party provider.

    This intentionally conservative hook can later be replaced by Presidio or an
    organization-specific recognizer without changing provider adapters.
    """
    redacted = value or ""
    counts: Dict[str, int] = {}
    for name, pattern, replacement in _PATTERNS:
        redacted, count = pattern.subn(replacement, redacted)
        if count:
            counts[name] = count
    return redacted, counts
