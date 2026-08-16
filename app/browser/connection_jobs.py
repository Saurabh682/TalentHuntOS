"""Durable, non-blocking lifecycle for connected-site browser work."""

from __future__ import annotations

import threading
from typing import Any

from app.jobs import service as jobs

_controls_lock = threading.Lock()
_launch_lock = threading.Lock()
_connect_controls: dict[str, dict[str, threading.Event]] = {}


def _platform_config(platform: str) -> tuple[str, dict[str, Any]]:
    from app.browser.session_auth import PLATFORM_LOGIN

    normalized = (platform or "").strip().lower()
    config = PLATFORM_LOGIN.get(normalized)
    if not config:
        raise ValueError(f"Unsupported platform: {platform}")
    return normalized, config


def _active_site_job(
    platform: str,
    *,
    kinds: set[str] | None = None,
) -> dict[str, Any] | None:
    normalized, _ = _platform_config(platform)
    allowed = kinds or {"site_connect", "site_verify"}
    for row in jobs.list_job_rows(statuses={"running"}, limit=200):
        if row.kind not in allowed:
            continue
        item = jobs.serialize_job(row)
        if str(item.get("payload", {}).get("platform") or "").lower() == normalized:
            return item
    return None


def list_active_site_jobs() -> dict[str, dict[str, Any]]:
    """Return sanitized active browser work keyed by platform."""
    active: dict[str, dict[str, Any]] = {}
    for row in jobs.list_job_rows(statuses={"running"}, limit=200):
        if row.kind not in {"site_connect", "site_verify"}:
            continue
        item = jobs.serialize_job(row)
        platform = str(item.get("payload", {}).get("platform") or "").strip().lower()
        if not platform or platform in active:
            continue
        active[platform] = {
            "id": item["id"],
            "kind": item["kind"],
            "status": item["status"],
            "message": item["message"],
            "phase": item.get("phase"),
            "ready_for_save": bool(item.get("ready_for_save")),
            "window_open": bool(item.get("window_open")),
            "attempt": item.get("attempt") or 1,
        }
    return active


def start_site_connection(
    platform: str,
    *,
    actor_type: str,
    session_id: str | None,
    reconnect: bool = False,
    parent_job_id: str | None = None,
    attempt: int = 1,
    timeout_sec: int = 600,
) -> dict[str, Any]:
    """Start a visible-browser login without blocking Copilot or the UI."""
    normalized, config = _platform_config(platform)
    label = str(config["label"])
    mode = "reconnect" if reconnect else "connect"

    with _launch_lock:
        active_login = next(
            (
                jobs.serialize_job(row)
                for row in jobs.list_job_rows(statuses={"running"}, limit=200)
                if row.kind == "site_connect"
            ),
            None,
        )
        if active_login:
            raise RuntimeError(
                "Another interactive site login is already running "
                f"(job {active_login['id']}). Cancel or finish it first."
            )
        if _active_site_job(normalized, kinds={"site_verify"}):
            raise RuntimeError(f"{label} login verification is already running.")

        job_id = jobs.create_job(
            kind="site_connect",
            label=f"{mode.title()} {label}",
            payload={
                "platform": normalized,
                "mode": mode,
                "actor_type": actor_type,
                "session_id": session_id,
                "timeout_sec": max(60, min(int(timeout_sec), 900)),
            },
            attempt=attempt,
            parent_job_id=parent_job_id,
        )
        controls = {"save": threading.Event(), "cancel": threading.Event()}
        with _controls_lock:
            _connect_controls[job_id] = controls

    def _worker() -> None:
        from app.browser.session_auth import interactive_connect

        progress: dict[str, Any] = {
            "message": f"Opening a secure browser window for {label}...",
            "window_open": False,
            "login_page_loaded": False,
        }
        monitor_stop = threading.Event()

        def _monitor() -> None:
            while not monitor_stop.wait(0.35):
                ready = bool(progress.get("login_page_loaded"))
                fields = {
                    "message": str(progress.get("message") or "Waiting for browser login..."),
                    "phase": "waiting_for_login" if ready else "opening_browser",
                    "window_open": bool(progress.get("window_open")),
                    "ready_for_save": ready,
                    "browser_channel": progress.get("browser_channel"),
                    "platform": normalized,
                }
                if not jobs.update_running_job(job_id, fields):
                    break

        jobs.begin_running_phase(
            job_id,
            "opening_browser",
            message=f"Opening a secure browser window for {label}...",
        )
        monitor = threading.Thread(
            target=_monitor,
            daemon=True,
            name=f"site-connect-monitor-{job_id}",
        )
        monitor.start()
        try:
            result = interactive_connect(
                normalized,
                timeout_sec=max(60, min(int(timeout_sec), 900)),
                save_event=controls["save"],
                cancel_event=controls["cancel"],
                progress=progress,
            )
            result_status = str(result.get("status") or "error")
            if result_status == "success" and result.get("verified"):
                jobs.finish_job_record(
                    job_id,
                    status="done",
                    message=f"{label} login verified and encrypted locally.",
                    result={
                        "status": "verified",
                        "platform": normalized,
                        "verified": True,
                        "encrypted": True,
                        "session_id": result.get("session_id"),
                        "cookie_count": result.get("cookie_count", 0),
                    },
                )
            elif result_status == "cancelled":
                jobs.finish_job_record(
                    job_id,
                    status="cancelled",
                    message=f"{label} login was cancelled.",
                    result={"status": "cancelled", "platform": normalized},
                )
            else:
                error = str(result.get("error") or f"{label} login did not complete.")
                jobs.finish_job_record(
                    job_id,
                    status="error",
                    message=f"{label} login failed.",
                    error=error,
                    result={"status": result_status, "platform": normalized},
                )
        except Exception as exc:
            jobs.finish_job_record(
                job_id,
                status="error",
                message=f"{label} login failed.",
                error=str(exc),
            )
        finally:
            monitor_stop.set()
            monitor.join(timeout=1.0)
            with _controls_lock:
                _connect_controls.pop(job_id, None)

    threading.Thread(
        target=_worker,
        daemon=True,
        name=f"site-connect-{normalized}-{job_id}",
    ).start()
    return {
        "status": "started",
        "job_id": job_id,
        "kind": "site_connect",
        "platform": normalized,
        "label": label,
        "mode": mode,
        "attempt": attempt,
        "parent_job_id": parent_job_id,
        "message": (
            f"A visible browser is opening for {label}. Finish signing in there; "
            "the session will auto-save after verification."
        ),
    }


def start_site_verification(
    platform: str,
    *,
    actor_type: str,
    session_id: str | None,
    parent_job_id: str | None = None,
    attempt: int = 1,
) -> dict[str, Any]:
    """Start a headless login verification as a durable background job."""
    normalized, config = _platform_config(platform)
    label = str(config["label"])
    with _launch_lock:
        active = _active_site_job(normalized)
        if active:
            raise RuntimeError(f"{label} already has active browser work (job {active['id']}).")
        job_id = jobs.create_job(
            kind="site_verify",
            label=f"Verify {label}",
            payload={
                "platform": normalized,
                "actor_type": actor_type,
                "session_id": session_id,
            },
            attempt=attempt,
            parent_job_id=parent_job_id,
        )

    def _worker() -> None:
        from app.browser.session_auth import verify_platform_session

        def _cancelled() -> bool:
            row = jobs.get_job_row(job_id)
            return not row or row.status != "running"

        jobs.begin_running_phase(
            job_id,
            "verifying",
            message=f"Checking the saved {label} login...",
        )
        try:
            result = verify_platform_session(
                normalized,
                headless=True,
                cancel_check=_cancelled,
            )
            status = str(result.get("status") or "error")
            if status == "cancelled":
                jobs.finish_job_record(
                    job_id,
                    status="cancelled",
                    message=f"{label} login verification was cancelled.",
                    result={"status": "cancelled", "platform": normalized},
                )
            elif result.get("ok"):
                jobs.finish_job_record(
                    job_id,
                    status="done",
                    message=f"{label} login is verified.",
                    result={"status": "verified", "platform": normalized, "ok": True},
                )
            elif status in {"disconnected", "invalid", "expired"}:
                jobs.finish_job_record(
                    job_id,
                    status="done",
                    message=f"{label} login is {status}. Reconnect it before sourcing.",
                    result={"status": status, "platform": normalized, "ok": False},
                )
            else:
                jobs.finish_job_record(
                    job_id,
                    status="error",
                    message=f"{label} login verification failed.",
                    error=str(result.get("error") or "Verification failed."),
                    result={"status": status, "platform": normalized, "ok": False},
                )
        except Exception as exc:
            jobs.finish_job_record(
                job_id,
                status="error",
                message=f"{label} login verification failed.",
                error=str(exc),
            )

    threading.Thread(
        target=_worker,
        daemon=True,
        name=f"site-verify-{normalized}-{job_id}",
    ).start()
    return {
        "status": "started",
        "job_id": job_id,
        "kind": "site_verify",
        "platform": normalized,
        "label": label,
        "attempt": attempt,
        "parent_job_id": parent_job_id,
        "message": f"Checking the saved {label} login in the background.",
    }


def request_save(job_id: str) -> dict[str, Any]:
    """Signal one exact interactive login job to validate and save its session."""
    row = jobs.get_job_row(job_id)
    if not row or row.kind != "site_connect":
        raise ValueError("Site connection job not found.")
    if row.status != "running":
        raise ValueError(f"Job {job_id} is already {row.status}.")
    with _controls_lock:
        control = _connect_controls.get(job_id)
        if not control:
            raise RuntimeError(
                "The login browser is no longer attached to this application process."
            )
        control["save"].set()
    jobs.update_running_job(
        job_id,
        {"message": "Checking the current browser login before saving..."},
    )
    return {
        "status": "save_requested",
        "job_id": job_id,
        "platform": jobs.serialize_job(row).get("payload", {}).get("platform"),
        "message": "Save requested. The session is stored only after login verification succeeds.",
    }


def signal_cancel(job_id: str) -> bool:
    """Promptly close the browser loop for an exact connection job."""
    with _controls_lock:
        control = _connect_controls.get(job_id)
        if not control:
            return False
        control["cancel"].set()
        return True


def retry_site_job(original: dict[str, Any]) -> dict[str, Any]:
    """Replay a terminal site job from sanitized durable launch parameters."""
    payload = original.get("payload", {})
    platform = str(payload.get("platform") or "")
    next_attempt = int(original.get("attempt") or 1) + 1
    if original["kind"] == "site_connect":
        return start_site_connection(
            platform,
            actor_type=str(payload.get("actor_type") or "copilot"),
            session_id=payload.get("session_id"),
            reconnect=str(payload.get("mode") or "connect") == "reconnect",
            parent_job_id=original["id"],
            attempt=next_attempt,
            timeout_sec=int(payload.get("timeout_sec") or 600),
        )
    if original["kind"] == "site_verify":
        return start_site_verification(
            platform,
            actor_type=str(payload.get("actor_type") or "copilot"),
            session_id=payload.get("session_id"),
            parent_job_id=original["id"],
            attempt=next_attempt,
        )
    raise ValueError(f"Job kind '{original['kind']}' is not a site job.")
