"""Console logging setup for TalentHunt OS (so background jobs are visible in the terminal)."""

from __future__ import annotations

import logging
import sys


_configured = False


def configure_logging(level: int = logging.INFO) -> None:
    """Idempotent: attach a stdout handler for talenthunt.* + root warnings."""
    global _configured
    if _configured:
        return
    _configured = True

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(fmt)
    handler.setLevel(level)

    root = logging.getLogger()
    # Avoid duplicate handlers on reload
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
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
