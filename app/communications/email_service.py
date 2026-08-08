"""Mock SMTP / IMAP Email service for simulated email sending and inbox fetching."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


def send_email(
    to_email: str,
    subject: str,
    body: str,
    from_account: Optional[str] = None,
    cc: Optional[str] = None,
) -> Dict[str, Any]:
    """Mock sending an email via SMTP.
    
    Returns a result payload with status, generated message_id, timestamp, and details.
    """
    body = body or ""
    message_id = f"msg-{uuid.uuid4().hex[:12]}"
    sender = from_account or "recruiter@talenthunt.os"
    
    # Simple email validation logic simulation
    if not to_email or "@" not in to_email:
        return {
            "success": False,
            "status": "failed",
            "error": f"Invalid recipient email address: '{to_email}'",
            "message_id": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return {
        "success": True,
        "status": "sent",
        "message_id": message_id,
        "from": sender,
        "to": to_email,
        "cc": cc,
        "subject": subject,
        "body_snippet": body[:100] + "..." if len(body) > 100 else body,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "smtp_server": "smtp.talenthunt-mock.internal:587",
    }


def fetch_inbox(account_id: Optional[int] = None, limit: int = 5) -> List[Dict[str, Any]]:
    """Mock IMAP email fetching from recruiter inbox.
    
    Returns simulated list of recent candidate responses.
    """
    return []


def verify_email_connection(
    account_id: Optional[int] = None,
    smtp_host: str = "smtp.gmail.com",
    port: int = 587,
) -> Dict[str, Any]:
    """Mock verifying SMTP/IMAP credentials and connectivity."""
    return {
        "status": "connected",
        "smtp_status": "220 Ready to deliver",
        "imap_status": "OK Authenticated",
        "host": smtp_host,
        "port": port,
        "latency_ms": 42,
    }
