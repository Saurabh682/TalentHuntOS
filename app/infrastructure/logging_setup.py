"""Local console logging with optional JSON output and centralized redaction."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any

_configured = False

_BEARER_RE = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]+")
_KEY_VALUE_RE = re.compile(
    r"(?i)\b(api[_-]?key|authorization|password|passwd|token|secret|cookie|session(?:_id)?)"
    r"(\s*[:=]\s*)([^\s,;]+)"
)
_EMAIL_RE = re.compile(r"(?i)\b[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9.-]+\.[a-z]{2,}\b")
_COMMON_SECRET_RE = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{12,}|AIza[A-Za-z0-9_-]{20,})\b")


def redact_log_text(value: Any) -> str:
    """Return a log-safe string without common credentials or email PII."""
    text = str(value)
    text = _BEARER_RE.sub("Bearer <redacted>", text)
    text = _KEY_VALUE_RE.sub(lambda match: f"{match.group(1)}{match.group(2)}<redacted>", text)
    text = _COMMON_SECRET_RE.sub("<redacted-secret>", text)
    return _EMAIL_RE.sub("<redacted-email>", text)


class RedactingFilter(logging.Filter):
    """Render the final message once, redact it, and prevent raw args from leaking."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_log_text(record.getMessage())
        record.args = ()
        return True


class JsonLogFormatter(logging.Formatter):
    """Small JSON-lines formatter for local ingestion and troubleshooting."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))


def configure_logging(level: int = logging.INFO) -> None:
    """Attach one redacting stdout handler for TalentHunt and dependency warnings."""
    global _configured
    if _configured:
        return
    _configured = True

    output_format = os.getenv("TALENTHUNT_LOG_FORMAT", "console").strip().lower()
    fmt: logging.Formatter
    if output_format == "json":
        fmt = JsonLogFormatter()
    else:
        fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(fmt)
    handler.setLevel(level)
    handler.addFilter(RedactingFilter())
    handler._talenthunt_handler = True  # type: ignore[attr-defined]

    root = logging.getLogger()
    # Avoid duplicate handlers on reload
    if not any(getattr(h, "_talenthunt_handler", False) for h in root.handlers):
        root.addHandler(handler)
    root.setLevel(level)

    # Keep SQLAlchemy quiet unless debugging
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("primp").setLevel(logging.WARNING)

    # Ensure our package loggers propagate
    logging.getLogger("talenthunt").setLevel(level)
