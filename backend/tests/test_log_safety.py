import logging

from backend.app.security.log_safety import PrivacyLogFilter, privacy_fingerprint


def test_log_filter_redacts_emails_and_long_digit_strings():
    record = logging.LogRecord(
        "test", logging.INFO, __file__, 1,
        "query=%s account=%s", ("jane.doe@example.com", "123456789012"), None,
    )
    assert PrivacyLogFilter().filter(record) is True
    assert "jane.doe@example.com" not in record.getMessage()
    assert "123456789012" not in record.getMessage()
    assert "[REDACTED_EMAIL]" in record.getMessage()
    assert "[REDACTED_DIGITS]" in record.getMessage()
    assert record.args == ()


def test_privacy_fingerprint_is_stable_without_returning_the_value():
    first = privacy_fingerprint("private customer query")
    assert first == privacy_fingerprint("private customer query")
    assert first != privacy_fingerprint("different query")
    assert len(first) == 12
    assert "private" not in first
