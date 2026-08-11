"""SMTP delivery boundary with encrypted local account credentials."""

from __future__ import annotations

import smtplib
import ssl
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Any, Dict, List, Optional

from sqlalchemy import select


def _base_result(
    *,
    sender: str,
    to_email: str,
    subject: str,
    body: str,
    cc: Optional[str],
) -> Dict[str, Any]:
    return {
        "success": False,
        "delivered": False,
        "message_id": None,
        "from": sender,
        "to": to_email,
        "cc": cc,
        "subject": subject,
        "body_snippet": body[:100] + "..." if len(body) > 100 else body,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _connect(account, *, timeout: float = 15.0):
    """Open an encrypted SMTP transport; port 465 uses implicit TLS."""
    host = (account.smtp_host or "").strip()
    if not host:
        raise ValueError("SMTP host is missing.")
    context = ssl.create_default_context()
    if account.use_ssl and account.smtp_port == 465:
        client = smtplib.SMTP_SSL(host, account.smtp_port, timeout=timeout, context=context)
    else:
        client = smtplib.SMTP(host, account.smtp_port, timeout=timeout)
        client.ehlo()
        if account.use_ssl:
            client.starttls(context=context)
            client.ehlo()

    from app.infrastructure.secret_box import open_secret

    password = open_secret(account.smtp_password)
    username = (account.smtp_username or account.email_address or "").strip()
    if username and password:
        client.login(username, password)
    return client


def _load_account(db, from_account: Optional[str] = None):
    from app.communications.models import EmailAccount
    from app.communications.service import get_default_email_account

    if from_account:
        return db.scalar(
            select(EmailAccount).where(
                EmailAccount.email_address == from_account,
                EmailAccount.is_active.is_(True),
            )
        )
    account = get_default_email_account(db)
    return account if account and account.is_active else None


def send_email(
    to_email: str,
    subject: str,
    body: str,
    from_account: Optional[str] = None,
    cc: Optional[str] = None,
) -> Dict[str, Any]:
    """Send through a configured SMTP account and report the real outcome."""
    body = body or ""
    sender_hint = from_account or "recruiter@talenthunt.os"
    result = _base_result(
        sender=sender_hint,
        to_email=to_email,
        subject=subject,
        body=body,
        cc=cc,
    )
    if not to_email or "@" not in to_email:
        result.update({
            "status": "failed",
            "error": f"Invalid recipient email address: '{to_email}'",
        })
        return result

    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        account = _load_account(db, from_account)
        if not account or not account.smtp_password:
            result.update({
                "status": "not_configured",
                "error": "SMTP delivery is not configured. The communication can be logged, but was not sent.",
            })
            return result

        sender = account.email_address
        result["from"] = sender
        message_id = make_msgid(domain=sender.split("@", 1)[-1])
        message = EmailMessage()
        message["From"] = formataddr((account.display_name or "", sender))
        message["To"] = to_email
        if cc:
            message["Cc"] = cc
        message["Subject"] = subject
        message["Message-ID"] = message_id
        message.set_content(body)

        try:
            client = _connect(account)
            try:
                client.send_message(message)
            finally:
                try:
                    client.quit()
                except Exception:
                    client.close()
        except Exception as exc:
            result.update({"status": "failed", "error": f"SMTP delivery failed: {exc}"})
            return result

    result.update({
        "success": True,
        "delivered": True,
        "status": "sent",
        "error": None,
        "message_id": message_id,
    })
    return result


def fetch_inbox(account_id: Optional[int] = None, limit: int = 5) -> List[Dict[str, Any]]:
    """IMAP is not configured yet; never manufacture inbox messages."""
    return []


def verify_email_connection(
    account_id: Optional[int] = None,
    smtp_host: str = "smtp.gmail.com",
    port: int = 587,
) -> Dict[str, Any]:
    """Authenticate to SMTP without sending a message."""
    from app.communications.models import EmailAccount
    from app.infrastructure.db import SessionFactory

    with SessionFactory() as db:
        account = db.get(EmailAccount, account_id) if account_id else _load_account(db)
        if not account or not account.smtp_password:
            return {
                "status": "not_configured",
                "smtp_status": "Not configured",
                "imap_status": "Not configured",
                "host": smtp_host,
                "port": port,
                "latency_ms": None,
            }
        started = time.perf_counter()
        try:
            client = _connect(account)
            try:
                client.noop()
            finally:
                try:
                    client.quit()
                except Exception:
                    client.close()
        except Exception as exc:
            return {
                "status": "failed",
                "smtp_status": "Connection failed",
                "imap_status": "Not configured",
                "host": account.smtp_host,
                "port": account.smtp_port,
                "latency_ms": round((time.perf_counter() - started) * 1000),
                "error": str(exc),
            }
        return {
            "status": "connected",
            "smtp_status": "Connected",
            "imap_status": "Not configured",
            "host": account.smtp_host,
            "port": account.smtp_port,
            "latency_ms": round((time.perf_counter() - started) * 1000),
        }
