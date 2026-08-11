"""Browser automation helpers for TalentHunt OS."""

from app.browser.page_reader import open_page_and_read, enrich_profile_from_url
from app.browser.snapshots import (
    attach_pending_snapshot_to_candidate,
    list_snapshots_for_candidate,
    read_snapshot_text,
)
from app.browser.session_auth import (
    interactive_connect,
    get_platform_connection_status,
    disconnect_platform,
    verify_platform_session,
)

__all__ = [
    "open_page_and_read",
    "enrich_profile_from_url",
    "attach_pending_snapshot_to_candidate",
    "list_snapshots_for_candidate",
    "read_snapshot_text",
    "interactive_connect",
    "get_platform_connection_status",
    "disconnect_platform",
    "verify_platform_session",
]
