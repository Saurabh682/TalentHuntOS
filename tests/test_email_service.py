import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.communications.models import EmailAccount  # noqa: F401
from app.communications.service import save_email_account
from app.communications.email_service import send_email, fetch_inbox, verify_email_connection
from app.infrastructure.db import Base
from app.infrastructure.secret_box import is_sealed, open_secret
from app.hunts.models import TalentHunt  # noqa: F401


@pytest.fixture(autouse=True)
def isolated_email_database(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'email.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr("app.infrastructure.db.SessionFactory", factory)
    return factory

def test_send_email_fails_closed_when_smtp_is_not_configured():
    result = send_email(
        to_email="test@example.com",
        subject="Test Subject",
        body="This is a test body.",
    )
    assert result["success"] is False
    assert result["delivered"] is False
    assert result["status"] == "not_configured"
    assert result["message_id"] is None
    assert result["from"] == "recruiter@talenthunt.os"
    assert result["to"] == "test@example.com"
    assert result["cc"] is None
    assert result["subject"] == "Test Subject"
    assert result["body_snippet"] == "This is a test body."
    assert "timestamp" in result

def test_send_email_with_optional_params():
    result = send_email(
        to_email="test2@example.com",
        subject="Hello",
        body="A longer body " * 10,
        from_account="other@example.com",
        cc="cc@example.com",
    )
    assert result["success"] is False
    assert result["from"] == "other@example.com"
    assert result["cc"] == "cc@example.com"
    assert len(result["body_snippet"]) <= 103 # 100 chars + "..."

def test_send_email_invalid_recipient():
    result = send_email(
        to_email="invalidemail",
        subject="Test",
        body="Test",
    )
    assert result["success"] is False
    assert result["status"] == "failed"
    assert result["error"] == "Invalid recipient email address: 'invalidemail'"
    assert result["message_id"] is None

def test_send_email_empty_recipient():
    result = send_email(
        to_email="",
        subject="Test",
        body="Test",
    )
    assert result["success"] is False
    assert result["status"] == "failed"

def test_fetch_inbox_default():
    inbox = fetch_inbox()
    assert isinstance(inbox, list)
    assert inbox == []

def test_fetch_inbox_with_limit():
    inbox = fetch_inbox(limit=1)
    assert inbox == []

    inbox = fetch_inbox(limit=2)
    assert inbox == []

def test_verify_email_connection_default():
    result = verify_email_connection()
    assert result["status"] == "not_configured"
    assert result["smtp_status"] == "Not configured"
    assert result["imap_status"] == "Not configured"
    assert result["host"] == "smtp.gmail.com"
    assert result["port"] == 587
    assert result["latency_ms"] is None

def test_verify_email_connection_custom():
    result = verify_email_connection(account_id=1, smtp_host="smtp.example.com", port=465)
    assert result["status"] == "not_configured"
    assert result["host"] == "smtp.example.com"
    assert result["port"] == 465


def test_configured_smtp_is_encrypted_testable_and_delivers(
    isolated_email_database, monkeypatch
):
    events = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None, **kwargs):
            events.append(("connect", host, port))

        def ehlo(self):
            events.append(("ehlo",))

        def starttls(self, context=None):
            events.append(("starttls",))

        def login(self, username, password):
            events.append(("login", username, password))

        def noop(self):
            events.append(("noop",))

        def send_message(self, message):
            events.append(("send", message["To"], message["Subject"]))

        def quit(self):
            events.append(("quit",))

        def close(self):
            pass

    monkeypatch.setattr("app.communications.email_service.smtplib.SMTP", FakeSMTP)
    with isolated_email_database() as db:
        account = save_email_account(
            db,
            email_address="recruiter@example.com",
            display_name="Recruiter",
            smtp_host="smtp.example.com",
            smtp_port=587,
            smtp_username="smtp-user",
            smtp_password="app-secret",
            use_ssl=True,
        )
        account_id = account.id
        assert is_sealed(account.smtp_password)
        assert open_secret(account.smtp_password) == "app-secret"

    verified = verify_email_connection(account_id)
    assert verified["status"] == "connected"

    result = send_email("candidate@example.com", "Opportunity", "Hello")
    assert result["success"] is True
    assert result["delivered"] is True
    assert result["status"] == "sent"
    assert ("login", "smtp-user", "app-secret") in events
    assert ("send", "candidate@example.com", "Opportunity") in events
