"""Registered embedded local AI actions shared by Copilot and Settings."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.actions.context import ActionContext
from app.actions.registry import register_action


class EmptyInput(BaseModel):
    pass


class RuntimeInstallInput(BaseModel):
    acknowledge_download_gb: float = Field(
        ...,
        ge=2.0,
        le=2.2,
        description="Acknowledgement that the verified first-run download is about 2.1 GB.",
    )


class RuntimeConfigureInput(BaseModel):
    mode: Literal["lite", "standard", "external"]
    autostart: bool = True
    external_host: str | None = Field(default=None, max_length=80)
    external_port: int | None = Field(default=None, ge=1, le=65535)

    @model_validator(mode="after")
    def validate_external_endpoint(self) -> "RuntimeConfigureInput":
        from app.ai.local_server import _is_loopback_host

        if self.mode == "external":
            host = (self.external_host or "127.0.0.1").strip()
            if not _is_loopback_host(host):
                raise ValueError("External local AI host must be a literal loopback address.")
        elif self.external_host is not None or self.external_port is not None:
            raise ValueError("External host and port are accepted only in External mode.")
        return self


def _runtime_resource(data: BaseModel, ctx: ActionContext) -> list[str]:
    return ["ai-runtime:embedded"]


def _active_runtime_job_id() -> str | None:
    from app.jobs import service as jobs

    for row in jobs.list_job_rows(statuses={"running"}, limit=20):
        if row.kind in {"embedded_ai_install", "embedded_ai_start"}:
            return str(row.id)
    return None


@register_action(
    "ai.runtime.status",
    description=(
        "Read non-secret embedded local AI installation, verification, hardware, job, and "
        "loopback server health. Never returns local paths or artifact URLs."
    ),
    input_model=EmptyInput,
    classification="query",
    risk_level="R0",
    required_scopes=("read",),
    copilot_enabled=True,
    copilot_tool_name="get_embedded_ai_status",
)
def embedded_ai_status_action(data: EmptyInput, ctx: ActionContext) -> dict[str, Any]:
    from app.ai.embedded_runtime import public_status

    return public_status()


@register_action(
    "ai.runtime.install",
    description=(
        "Start one durable, cancellable installation of the pinned llama.cpp runtime and "
        "IBM Granite 4.1 3B Q4_K_M model. URLs and paths are fixed by the signed-in app."
    ),
    input_model=RuntimeInstallInput,
    resource_resolver=_runtime_resource,
    classification="ai_task",
    risk_level="R2",
    required_scopes=("write", "compute"),
    lock_ttl_seconds=60 * 60,
    copilot_enabled=True,
    copilot_tool_name="install_embedded_ai",
)
def install_embedded_ai_action(
    data: RuntimeInstallInput, ctx: ActionContext
) -> dict[str, Any]:
    from app.ai.embedded_jobs import start_embedded_ai_install
    from app.ai.embedded_runtime import EMBEDDED_MODES
    from app.config.settings import settings

    if settings.local_ai_mode not in EMBEDDED_MODES:
        raise ValueError("Select Lite or Standard mode before installing embedded AI.")
    result = start_embedded_ai_install(
        actor_type=ctx.actor_type,
        session_id=ctx.session_id,
    )
    return {
        **result,
        "download_size_gb": round(data.acknowledge_download_gb, 1),
        "message": (
            "Embedded AI installation started. Normal chat remains available; use Work "
            "History with the exact job ID to monitor or cancel it."
        ),
    }


@register_action(
    "ai.runtime.start",
    description="Verify and start the installed embedded local Copilot in a durable background job.",
    input_model=EmptyInput,
    resource_resolver=_runtime_resource,
    classification="ai_task",
    risk_level="R1",
    required_scopes=("write", "compute"),
    lock_ttl_seconds=20 * 60,
    copilot_enabled=True,
    copilot_tool_name="start_embedded_ai",
)
def start_embedded_ai_action(data: EmptyInput, ctx: ActionContext) -> dict[str, Any]:
    from app.ai.embedded_jobs import start_embedded_ai_server

    return start_embedded_ai_server(
        actor_type=ctx.actor_type,
        session_id=ctx.session_id,
    )


@register_action(
    "ai.runtime.stop",
    description=(
        "Stop only the embedded llama-server subprocess owned by this TalentHunt process. "
        "Never terminates LM Studio, Ollama, or another external process."
    ),
    input_model=EmptyInput,
    resource_resolver=_runtime_resource,
    classification="system",
    risk_level="R2",
    required_scopes=("write", "compute"),
    copilot_enabled=True,
    copilot_tool_name="stop_embedded_ai",
)
def stop_embedded_ai_action(data: EmptyInput, ctx: ActionContext) -> dict[str, Any]:
    from app.ai.local_server import local_server_manager

    before = local_server_manager.get_status()
    if not before["managed"]:
        if before["status"] in {"external", "port_conflict"}:
            raise ValueError("TalentHunt does not own the local AI process on this port.")
        return {"status": "already_stopped", "server": before}
    if not local_server_manager.stop():
        raise RuntimeError(local_server_manager.last_error or "Embedded AI did not stop.")
    return {
        "status": "stopped",
        "message": "The TalentHunt-owned embedded AI process stopped.",
        "server": local_server_manager.get_status(),
    }


@register_action(
    "ai.runtime.configure",
    description=(
        "Set Lite, Standard, or loopback-only External local AI mode and autostart. "
        "The previous local preference remains undoable for seven days."
    ),
    input_model=RuntimeConfigureInput,
    resource_resolver=_runtime_resource,
    classification="mutation",
    risk_level="R2",
    required_scopes=("write",),
    copilot_enabled=True,
    copilot_tool_name="configure_embedded_ai",
)
def configure_embedded_ai_action(
    data: RuntimeConfigureInput, ctx: ActionContext
) -> dict[str, Any]:
    from app.actions.history import record_action
    from app.ai.embedded_runtime import hardware_profile, public_status
    from app.ai.local_server import local_server_manager
    from app.config.preferences import save_app_preferences
    from app.config.settings import settings
    from app.infrastructure.db import SessionFactory

    active_job_id = _active_runtime_job_id()
    if active_job_id:
        raise ValueError(
            f"Embedded AI job {active_job_id} is active. Cancel it before changing mode."
        )
    hardware = hardware_profile()
    if data.mode != "external" and not hardware["supported"]:
        raise ValueError(str(hardware["reason"]))

    previous = {
        "mode": settings.local_ai_mode,
        "autostart": bool(settings.local_ai_autostart),
        "host": settings.llama_server_host,
        "port": int(settings.llama_server_port),
    }
    next_state = {
        "mode": data.mode,
        "autostart": bool(data.autostart),
        "host": (
            (data.external_host or "127.0.0.1").strip()
            if data.mode == "external"
            else "127.0.0.1"
        ),
        "port": int(data.external_port or settings.llama_server_port),
    }
    if previous == next_state:
        return {"status": "unchanged", "runtime": public_status()}

    local_server_manager.stop()
    settings.local_ai_mode = next_state["mode"]
    settings.local_ai_autostart = next_state["autostart"]
    settings.llama_server_host = next_state["host"]
    settings.llama_server_port = next_state["port"]
    save_app_preferences()

    with SessionFactory() as db:
        history = record_action(
            db,
            action_type="configure_embedded_ai",
            summary=f"Configured local AI for {data.mode.title()} mode",
            payload={"previous": previous, "current": next_state},
            undo_payload={"previous": previous, "current": next_state},
            actor_type=ctx.actor_type,
            session_id=ctx.session_id,
        )
    return {
        "status": "updated",
        "action_id": history.id,
        "undo_days": 7,
        "runtime": public_status(),
        "message": "Local AI configuration saved. Start the runtime to apply the new mode.",
    }
