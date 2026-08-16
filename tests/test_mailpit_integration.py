"""Opt-in delivery test against the bounded loopback Mailpit instance."""

from __future__ import annotations

import os
import time
import urllib.error
import urllib.parse
import urllib.request
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.communications.email_service import (
    _allows_passwordless_smtp,
    send_email,
    verify_email_connection,
)
from app.communications.models import EmailAccount  # noqa: F401
from app.communications.service import save_email_account
from app.hunts.models import TalentHunt  # noqa: F401
from app.infrastructure.db import Base


@pytest.mark.parametrize(
    ("host", "allowed"),
    [
        ("127.0.0.1", True),
        ("::1", True),
        ("localhost", True),
        ("smtp.example.com", False),
        ("192.168.1.10", False),
    ],
)
def test_passwordless_smtp_is_limited_to_literal_loopback_hosts(host, allowed):
    account = SimpleNamespace(smtp_host=host)
    assert _allows_passwordless_smtp(account) is allowed


@pytest.mark.skipif(
    os.getenv("RUN_MAILPIT_TESTS") != "1",
    reason="Set RUN_MAILPIT_TESTS=1 after starting the loopback Mailpit helper.",
)
@pytest.mark.mailpit
def test_talenthunt_delivers_synthetic_mail_to_loopback_mailpit(monkeypatch, tmp_path):
    host = os.getenv("MAILPIT_SMTP_HOST", "127.0.0.1")
    port = int(os.getenv("MAILPIT_SMTP_PORT", "1025"))
    api_url = os.getenv("MAILPIT_API_URL", "http://127.0.0.1:8025")

    engine = create_engine(f"sqlite:///{tmp_path / 'mailpit.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr("app.infrastructure.db.SessionFactory", factory)

    with factory() as db:
        account = save_email_account(
            db,
            email_address="recruiter@talenthunt.test",
            display_name="TalentHunt Test",
            smtp_host=host,
            smtp_port=port,
            smtp_username="",
            smtp_password=None,
            use_ssl=False,
            is_default=True,
        )
        assert account is not None
        account_id = account.id

    assert verify_email_connection(account_id)["status"] == "connected"

    recipient = f"candidate-{uuid4().hex}@example.test"
    subject = f"TalentHunt Mailpit check {uuid4().hex}"
    result = send_email(recipient, subject, "Synthetic local integration message.")
    assert result["delivered"] is True

    query = urllib.parse.urlencode({"query": f'to:"{recipient}"'})
    latest_url = f"{api_url.rstrip('/')}/view/latest.txt?{query}"
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(latest_url, timeout=1) as response:  # noqa: S310
                body = response.read().decode("utf-8")
            assert "Synthetic local integration message." in body
            return
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
            time.sleep(0.1)
    pytest.fail("Mailpit did not expose the delivered message within 3 seconds")
