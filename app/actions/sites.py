"""Governed connected-site actions shared by Copilot and Settings."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.actions.context import ActionContext
from app.actions.registry import register_action

Platform = Literal["linkedin", "naukri", "github", "indeed"]


class SiteListInput(BaseModel):
    platform: Platform | None = None


class SitePlatformInput(BaseModel):
    platform: Platform


class SiteConnectInput(SitePlatformInput):
    timeout_sec: int = Field(default=600, ge=60, le=900)


class SiteJobInput(BaseModel):
    job_id: str = Field(min_length=6, max_length=32)

    @field_validator("job_id")
    @classmethod
    def valid_job_id(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized.isalnum():
            raise ValueError("job_id must contain only letters and numbers")
        return normalized


def _actor(ctx: ActionContext) -> str:
    return "copilot" if ctx.actor_type == "agent" else ctx.actor_type


def _site_resources(data: SitePlatformInput, ctx: ActionContext) -> list[str]:
    return [f"site:{data.platform}"]


def _site_connect_resources(data: SiteConnectInput, ctx: ActionContext) -> list[str]:
    return ["browser:interactive-login", f"site:{data.platform}"]


def _site_job_resources(data: SiteJobInput, ctx: ActionContext) -> list[str]:
    from app.jobs import service as jobs

    row = jobs.get_job_row(data.job_id)
    if not row or row.kind != "site_connect":
        raise ValueError("Site connection job not found.")
    platform = str(jobs.serialize_job(row).get("payload", {}).get("platform") or "unknown")
    return [f"job:{data.job_id}", f"site:{platform}"]


def _public_site_row(row: dict[str, Any], active_job: dict[str, Any] | None) -> dict[str, Any]:
    """Expose connection health without returning cookies, headers, or internal session rows."""
    return {
        "platform": row["platform"],
        "label": row["label"],
        "status": row.get("status") or "disconnected",
        "encrypted": bool(row.get("encrypted")),
        "verified": bool(row.get("verified")),
        "last_accessed_at": row.get("last_accessed_at"),
        "verified_at": row.get("verified_at"),
        "verify_detail": row.get("verify_detail"),
        "active_job": active_job,
        "available_actions": {
            "connect": row.get("status") == "disconnected" and active_job is None,
            "reconnect": row.get("status") != "disconnected" and active_job is None,
            "verify": row.get("status") in {"connected", "verified", "invalid"}
            and active_job is None,
            "disconnect": row.get("status") != "disconnected" and active_job is None,
            "cancel_job": bool(active_job),
        },
    }


def _site_status(platform: str) -> dict[str, Any]:
    from app.browser.connection_jobs import list_active_site_jobs
    from app.browser.session_auth import get_platform_connection_status

    active = list_active_site_jobs()
    for row in get_platform_connection_status():
        if row["platform"] == platform:
            return _public_site_row(row, active.get(platform))
    raise ValueError(f"Unsupported platform: {platform}")


def _preview_disconnect(data: SitePlatformInput, ctx: ActionContext) -> dict[str, Any]:
    site = _site_status(data.platform)
    if site.get("active_job"):
        raise ValueError(
            f"Cancel active job {site['active_job']['id']} before disconnecting {site['label']}."
        )
    if site["status"] == "disconnected":
        raise ValueError(f"{site['label']} is already disconnected.")
    return {
        "title": f"Disconnect {site['label']}",
        "summary": (
            f"Deactivate the saved {site['label']} browser session. "
            "Encrypted session data is retained locally for seven-day Undo."
        ),
        "platform": data.platform,
        "current_status": site["status"],
        "encrypted": site["encrypted"],
        "reversible": True,
        "undo_window_days": 7,
        "risk_level": "R3",
        "affected_resources": [f"site:{data.platform}"],
    }


@register_action(
    "sites.list",
    description=(
        "List sanitized connection and verification health for supported sourcing sites. "
        "Never returns cookies, headers, passwords, or credential values."
    ),
    input_model=SiteListInput,
    classification="query",
    risk_level="R0",
    required_scopes=("read",),
    copilot_enabled=True,
    copilot_tool_name="list_connected_sites",
)
def list_connected_sites_action(data: SiteListInput, ctx: ActionContext) -> dict[str, Any]:
    from app.browser.connection_jobs import list_active_site_jobs
    from app.browser.session_auth import get_platform_connection_status

    active = list_active_site_jobs()
    sites = [
        _public_site_row(row, active.get(row["platform"]))
        for row in get_platform_connection_status()
        if data.platform is None or row["platform"] == data.platform
    ]
    return {
        "status": "success",
        "count": len(sites),
        "sites": sites,
        "storage_policy": "Encrypted local cookies only; passwords are never stored.",
    }


@register_action(
    "sites.connect",
    description=(
        "Start a non-blocking visible-browser login for a disconnected sourcing site. "
        "The user signs in directly on the site; TalentHunt never receives the password."
    ),
    input_model=SiteConnectInput,
    resource_resolver=_site_connect_resources,
    classification="system",
    risk_level="R2",
    required_scopes=("write", "compute"),
    copilot_enabled=True,
    copilot_tool_name="connect_site_login",
)
def connect_site_action(data: SiteConnectInput, ctx: ActionContext) -> dict[str, Any]:
    from app.browser.connection_jobs import start_site_connection

    site = _site_status(data.platform)
    if site["status"] != "disconnected":
        raise ValueError(f"{site['label']} already has saved session state. Use Reconnect instead.")
    return start_site_connection(
        data.platform,
        actor_type=_actor(ctx),
        session_id=ctx.session_id,
        reconnect=False,
        timeout_sec=data.timeout_sec,
    )


@register_action(
    "sites.reconnect",
    description=(
        "Start a non-blocking visible-browser login to replace a saved or expired site session "
        "only after the new login is verified."
    ),
    input_model=SiteConnectInput,
    resource_resolver=_site_connect_resources,
    classification="system",
    risk_level="R2",
    required_scopes=("write", "compute"),
    copilot_enabled=True,
    copilot_tool_name="reconnect_site_login",
)
def reconnect_site_action(data: SiteConnectInput, ctx: ActionContext) -> dict[str, Any]:
    from app.browser.connection_jobs import start_site_connection

    return start_site_connection(
        data.platform,
        actor_type=_actor(ctx),
        session_id=ctx.session_id,
        reconnect=True,
        timeout_sec=data.timeout_sec,
    )


@register_action(
    "sites.verify",
    description=(
        "Start a non-blocking headless verification of one saved sourcing-site login. "
        "Returns a durable job ID for status or cancellation."
    ),
    input_model=SitePlatformInput,
    resource_resolver=_site_resources,
    classification="system",
    risk_level="R2",
    required_scopes=("read", "write", "compute"),
    copilot_enabled=True,
    copilot_tool_name="verify_site_login",
)
def verify_site_action(data: SitePlatformInput, ctx: ActionContext) -> dict[str, Any]:
    from app.browser.connection_jobs import start_site_verification

    site = _site_status(data.platform)
    if site["status"] == "disconnected":
        raise ValueError(f"{site['label']} has no saved session to verify. Connect it first.")
    return start_site_verification(
        data.platform,
        actor_type=_actor(ctx),
        session_id=ctx.session_id,
    )


@register_action(
    "sites.connect.save",
    description=(
        "Ask one exact active site-login job to verify and save the browser session. "
        "Saving is refused while the browser is still on a login page."
    ),
    input_model=SiteJobInput,
    resource_resolver=_site_job_resources,
    classification="mutation",
    risk_level="R2",
    required_scopes=("write", "compute"),
    copilot_enabled=True,
    copilot_tool_name="save_site_login",
)
def save_site_connection_action(data: SiteJobInput, ctx: ActionContext) -> dict[str, Any]:
    from app.browser.connection_jobs import request_save

    return request_save(data.job_id)


@register_action(
    "sites.disconnect",
    description=(
        "Disconnect one saved sourcing-site login while retaining encrypted local data for "
        "seven-day Undo."
    ),
    input_model=SitePlatformInput,
    preview_handler=_preview_disconnect,
    resource_resolver=_site_resources,
    requires_approval=True,
    classification="mutation",
    risk_level="R3",
    required_scopes=("write",),
    copilot_enabled=True,
    copilot_tool_name="disconnect_site",
)
def disconnect_site_action(data: SitePlatformInput, ctx: ActionContext) -> dict[str, Any]:
    from app.browser.connection_jobs import list_active_site_jobs
    from app.browser.session_auth import disconnect_platform

    active = list_active_site_jobs().get(data.platform)
    if active:
        raise ValueError(f"Cancel active job {active['id']} before disconnecting this site.")
    result = disconnect_platform(
        data.platform,
        actor_type=_actor(ctx),
        session_id=ctx.session_id,
    )
    if result.get("deactivated", 0) < 1:
        raise ValueError(f"{data.platform.title()} is already disconnected.")
    return {
        **result,
        "message": (
            f"{data.platform.title()} disconnected. Encrypted session data can be restored "
            "from Action History for seven days."
        ),
        "reversible": True,
        "undo_window_days": 7,
    }
