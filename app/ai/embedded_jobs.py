"""Durable background jobs for embedded local Copilot installation and startup."""

from __future__ import annotations

import threading
from typing import Any

from app.ai.embedded_runtime import (
    EMBEDDED_MODES,
    DownloadCancelled,
    hardware_profile,
    install_embedded_components,
    model_state,
    public_status,
    resolve_verified_runtime,
)
from app.ai.local_server import local_server_manager
from app.jobs import service as jobs

_LAUNCH_LOCK = threading.Lock()
_WORK_LOCK = threading.Lock()
_KINDS = {"embedded_ai_install", "embedded_ai_start"}


def _running_runtime_job() -> dict[str, Any] | None:
    for row in jobs.list_job_rows(statuses={"running"}, limit=30):
        if row.kind in _KINDS:
            return jobs.serialize_job(row)
    return None


def _job_cancelled(job_id: str) -> bool:
    row = jobs.get_job_row(job_id)
    return not row or row.status != "running"


def _update(job_id: str, values: dict[str, Any]) -> None:
    message_by_phase = {
        "downloading_runtime": "Downloading the verified local AI engine...",
        "verifying_downloading_runtime": "Verifying the local AI engine...",
        "downloading_model": "Downloading IBM Granite 4.1 3B...",
        "verifying_downloading_model": "Verifying the Granite model...",
        "verifying_model": "Verifying the installed Granite model...",
        "starting": "Starting the embedded local Copilot...",
    }
    phase = str(values.get("phase") or "")
    payload = dict(values)
    if phase in message_by_phase:
        payload["message"] = message_by_phase[phase]
    jobs.update_running_job(job_id, payload)


def _create_runtime_job(
    *,
    kind: str,
    label: str,
    actor_type: str,
    session_id: str | None,
    parent_job_id: str | None,
    attempt: int,
) -> str:
    with _LAUNCH_LOCK:
        active = _running_runtime_job()
        if active:
            raise RuntimeError(
                f"Embedded AI work is already running as job {active['id']}."
            )
        return jobs.create_job(
            kind=kind,
            label=label,
            payload={"actor_type": actor_type, "session_id": session_id},
            attempt=attempt,
            parent_job_id=parent_job_id,
        )


def start_embedded_ai_install(
    *,
    actor_type: str,
    session_id: str | None,
    parent_job_id: str | None = None,
    attempt: int = 1,
) -> dict[str, Any]:
    """Start one cancellable, restart-truthful runtime and model installation."""
    hardware = hardware_profile()
    if not hardware["supported"]:
        raise RuntimeError(str(hardware["reason"]))
    job_id = _create_runtime_job(
        kind="embedded_ai_install",
        label="Install Embedded Local Copilot",
        actor_type=actor_type,
        session_id=session_id,
        parent_job_id=parent_job_id,
        attempt=attempt,
    )

    def _worker() -> None:
        try:
            with _WORK_LOCK:
                components = install_embedded_components(
                    progress=lambda values: _update(job_id, values),
                    cancel_check=lambda: _job_cancelled(job_id),
                )
                if _job_cancelled(job_id):
                    return
                jobs.begin_running_phase(
                    job_id,
                    "starting",
                    message="Starting the embedded local Copilot...",
                )
                started = local_server_manager.start(
                    model_verified=True,
                    cancel_check=lambda: _job_cancelled(job_id),
                )
                if _job_cancelled(job_id):
                    local_server_manager.stop()
                    return
                status = public_status()
                jobs.finish_job_record(
                    job_id,
                    status="done" if started else "error",
                    message=(
                        "Embedded Local Copilot is installed and ready."
                        if started
                        else "Embedded components installed, but the server did not start."
                    ),
                    error=None if started else local_server_manager.last_error,
                    result={
                        **components,
                        "server_status": status["server"]["status"],
                        "mode": status["mode"],
                    },
                )
        except DownloadCancelled:
            jobs.cancel_job(
                job_id,
                message="Embedded AI installation cancelled. Partial download retained for Retry.",
            )
        except Exception as exc:
            jobs.finish_job_record(
                job_id,
                status="error",
                message="Embedded Local Copilot installation failed.",
                error=str(exc),
            )

    threading.Thread(
        target=_worker,
        daemon=True,
        name=f"embedded-ai-install-{job_id}",
    ).start()
    return {
        "status": "started",
        "job_id": job_id,
        "kind": "embedded_ai_install",
        "attempt": attempt,
        "parent_job_id": parent_job_id,
    }


def start_embedded_ai_server(
    *,
    actor_type: str,
    session_id: str | None,
    parent_job_id: str | None = None,
    attempt: int = 1,
) -> dict[str, Any]:
    """Verify and start the installed model without blocking chat or Settings."""
    from app.config.settings import settings

    if settings.local_ai_mode not in EMBEDDED_MODES:
        raise ValueError("Select Lite or Standard mode before starting embedded AI.")
    if not resolve_verified_runtime(full_verify=False)["verified"]:
        raise ValueError("The embedded llama.cpp runtime is not installed or verified.")
    if not model_state(full_verify=False)["verified"]:
        raise ValueError("The default Granite model is not installed or verified.")
    if local_server_manager.get_status()["status"] == "running":
        return {
            "status": "already_running",
            "kind": "embedded_ai_start",
            "job_id": None,
        }
    job_id = _create_runtime_job(
        kind="embedded_ai_start",
        label="Start Embedded Local Copilot",
        actor_type=actor_type,
        session_id=session_id,
        parent_job_id=parent_job_id,
        attempt=attempt,
    )

    def _worker() -> None:
        try:
            with _WORK_LOCK:
                verified = model_state(
                    full_verify=True,
                    progress=lambda values: _update(job_id, values),
                    cancel_check=lambda: _job_cancelled(job_id),
                )["verified"]
                if not verified:
                    raise RuntimeError("The installed Granite model failed verification.")
                if _job_cancelled(job_id):
                    return
                jobs.begin_running_phase(
                    job_id,
                    "starting",
                    message="Starting the embedded local Copilot...",
                )
                started = local_server_manager.start(
                    model_verified=True,
                    cancel_check=lambda: _job_cancelled(job_id),
                )
                if _job_cancelled(job_id):
                    local_server_manager.stop()
                    return
                jobs.finish_job_record(
                    job_id,
                    status="done" if started else "error",
                    message=(
                        "Embedded Local Copilot is ready."
                        if started
                        else "Embedded Local Copilot failed to start."
                    ),
                    error=None if started else local_server_manager.last_error,
                    result={"server_status": "running" if started else "stopped"},
                )
        except DownloadCancelled:
            jobs.cancel_job(job_id, message="Embedded AI startup cancelled.")
        except Exception as exc:
            jobs.finish_job_record(
                job_id,
                status="error",
                message="Embedded Local Copilot failed to start.",
                error=str(exc),
            )

    threading.Thread(
        target=_worker,
        daemon=True,
        name=f"embedded-ai-start-{job_id}",
    ).start()
    return {
        "status": "started",
        "job_id": job_id,
        "kind": "embedded_ai_start",
        "attempt": attempt,
        "parent_job_id": parent_job_id,
    }


def cancel_embedded_ai_job(job_id: str) -> dict[str, Any]:
    row = jobs.get_job_row(job_id)
    if not row or row.kind not in _KINDS:
        raise ValueError("Embedded AI job not found.")
    if not jobs.cancel_job(
        job_id,
        message=(
            "Embedded AI installation cancelled. Partial download retained for Retry."
            if row.kind == "embedded_ai_install"
            else "Embedded AI startup cancelled."
        ),
    ):
        raise ValueError(f"Job {job_id} is already {row.status}.")
    if row.kind == "embedded_ai_start":
        local_server_manager.stop()
    return {
        "status": "cancelled",
        "job_id": job_id,
        "kind": row.kind,
        "message": "Embedded AI work cancelled safely.",
    }


def retry_embedded_ai_job(original: dict[str, Any]) -> dict[str, Any]:
    payload = original.get("payload") or {}
    common = {
        "actor_type": str(payload.get("actor_type") or "copilot"),
        "session_id": payload.get("session_id"),
        "parent_job_id": str(original["id"]),
        "attempt": int(original.get("attempt") or 1) + 1,
    }
    if original["kind"] == "embedded_ai_install":
        return start_embedded_ai_install(**common)
    if original["kind"] == "embedded_ai_start":
        return start_embedded_ai_server(**common)
    raise ValueError("Unsupported embedded AI Retry job.")


def schedule_embedded_ai_autostart() -> dict[str, Any] | None:
    """Start the installed runtime after app startup without downloading anything."""
    from app.config.settings import settings

    if (
        not settings.enable_local_ai
        or not settings.local_ai_autostart
        or settings.local_ai_mode not in EMBEDDED_MODES
    ):
        return None
    if not resolve_verified_runtime(full_verify=False)["verified"]:
        return None
    if not model_state(full_verify=False)["verified"]:
        return None
    try:
        return start_embedded_ai_server(actor_type="system", session_id=None)
    except RuntimeError:
        return None
