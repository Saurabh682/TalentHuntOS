import pytest
from datetime import datetime
from app.communications.email_service import send_email, fetch_inbox, verify_email_connection

def test_send_email_success():
    result = send_email(
        to_email="test@example.com",
        subject="Test Subject",
        body="This is a test body.",
    )
    assert result["success"] is True
    assert result["status"] == "sent"
    assert "message_id" in result
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
    assert result["success"] is True
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
    assert len(inbox) == 3
    assert inbox[0]["message_id"] == "msg-inbound-001"

def test_fetch_inbox_with_limit():
    inbox = fetch_inbox(limit=1)
    assert len(inbox) == 1
    assert inbox[0]["message_id"] == "msg-inbound-001"

    inbox = fetch_inbox(limit=2)
    assert len(inbox) == 2

def test_verify_email_connection_default():
    result = verify_email_connection()
    assert result["status"] == "connected"
    assert result["smtp_status"] == "220 Ready to deliver"
    assert result["imap_status"] == "OK Authenticated"
    assert result["host"] == "smtp.gmail.com"
    assert result["port"] == 587
    assert "latency_ms" in result

def test_verify_email_connection_custom():
    result = verify_email_connection(account_id=1, smtp_host="smtp.example.com", port=465)
    assert result["status"] == "connected"
    assert result["host"] == "smtp.example.com"
    assert result["port"] == 465
