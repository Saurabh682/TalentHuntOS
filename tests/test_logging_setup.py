import json
import logging

from app.infrastructure.logging_setup import JsonLogFormatter, RedactingFilter, redact_log_text


def test_redact_log_text_removes_credentials_and_email_pii():
    raw = (
        "password=hunter2 token:abc123 Authorization=Bearer-secret "
        "Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig recruiter@example.com sk-abcdefghijklmnop"
    )
    redacted = redact_log_text(raw)

    assert "hunter2" not in redacted
    assert "abc123" not in redacted
    assert "Bearer-secret" not in redacted
    assert "eyJhbGci" not in redacted
    assert "recruiter@example.com" not in redacted
    assert "sk-abcdefghijklmnop" not in redacted
    assert redacted.count("<redacted") >= 5


def test_filter_redacts_formatted_arguments_before_formatter_reads_them():
    record = logging.LogRecord(
        name="talenthunt.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Login for %s with token=%s",
        args=("person@example.com", "secret-token"),
        exc_info=None,
    )

    assert RedactingFilter().filter(record) is True
    assert record.args == ()
    assert "person@example.com" not in record.getMessage()
    assert "secret-token" not in record.getMessage()


def test_json_formatter_emits_machine_readable_redacted_message():
    record = logging.LogRecord(
        name="talenthunt.test",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="API_KEY=very-secret user@example.com",
        args=(),
        exc_info=None,
    )
    RedactingFilter().filter(record)
    payload = json.loads(JsonLogFormatter().format(record))

    assert payload["level"] == "WARNING"
    assert payload["logger"] == "talenthunt.test"
    assert "very-secret" not in payload["message"]
    assert "user@example.com" not in payload["message"]
