"""Settings controls for the action-backed Embedded Local Copilot runtime."""

from __future__ import annotations

from typing import Any

from nicegui import ui

from app.actions.api import dispatch_action

SESSION_ID = "settings-embedded-ai"


def _format_bytes(value: int | float | None) -> str:
    amount = float(value or 0)
    if amount >= 1024**3:
        return f"{amount / (1024**3):.1f} GB"
    if amount >= 1024**2:
        return f"{amount / (1024**2):.0f} MB"
    return f"{amount / 1024:.0f} KB"


def _read_status() -> dict[str, Any]:
    result = dispatch_action(
        "ai.runtime.status",
        {},
        actor_type="ui",
        session_id=SESSION_ID,
    )
    if not result.success:
        raise RuntimeError(result.error or "Embedded AI status is unavailable.")
    return dict(result.data)


def render_embedded_ai_panel() -> None:
    """Render one quiet control surface for embedded and external local AI."""
    initial = _read_status()
    hardware = initial["hardware"]

    with ui.card().classes("w-full p-5 th-card mb-[13px]"):
        with ui.row().classes("items-center justify-between w-full gap-3 mb-1"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("memory", color="teal-4", size="sm")
                ui.label("Embedded Local Copilot").classes(
                    "text-[13px] font-semibold text-[#edf5f7]"
                )
            status_label = ui.label("Checking").classes("text-[#8de8df] text-[10px]")

        ui.label("IBM Granite 4.1 3B Q4_K_M · llama.cpp · private local storage").classes(
            "th-muted mb-3"
        )

        with ui.row().classes("w-full gap-5 items-start flex-wrap"):
            with ui.column().classes("grow min-w-[280px] gap-2"):
                ui.label("Runtime mode").classes("th-caption")
                mode_toggle = ui.toggle(
                    {"lite": "Lite", "standard": "Standard", "external": "External"},
                    value=initial["mode"],
                ).props("no-caps spread")
                mode_note = ui.label(hardware["reason"]).classes("th-muted")
            with ui.column().classes("min-w-[210px] gap-2"):
                ui.label("Detected hardware").classes("th-caption")
                ui.label(
                    f"{hardware['ram_gb']} GB RAM · {hardware['cpu_threads']} CPU threads"
                ).classes("text-[12px] text-[#edf5f7]")
                ui.label(f"Recommended: {hardware['recommended_mode'].title()}").classes(
                    "text-[11px] text-[#45d6a0]"
                )

        external_row = ui.row().classes("w-full gap-3 items-end mt-2")
        with external_row:
            with ui.column().classes("grow gap-1"):
                ui.label("Loopback host").classes("th-caption")
                host_input = (
                    ui.input(value=initial["external_endpoint"]["host"], placeholder="127.0.0.1")
                    .classes("w-full")
                    .props("outlined dark dense")
                )
            with ui.column().classes("w-32 gap-1"):
                ui.label("Port").classes("th-caption")
                port_input = (
                    ui.number(
                        value=initial["external_endpoint"]["port"],
                        min=1,
                        max=65535,
                        format="%.0f",
                    )
                    .classes("w-full")
                    .props("outlined dark dense")
                )
        external_row.set_visibility(initial["mode"] == "external")

        with ui.row().classes("w-full justify-between items-center gap-3 mt-3 flex-wrap"):
            with ui.row().classes("items-center gap-2"):
                autostart_switch = ui.switch(
                    "Start with TalentHunt", value=bool(initial["autostart"])
                ).props('aria-label="Start embedded AI with TalentHunt"')
            with ui.row().classes("items-center gap-1"):
                save_button = ui.button("Save", icon="save").classes("th-slate-btn")
                install_button = ui.button("Install", icon="download").classes("th-primary-btn")
                start_button = (
                    ui.button(icon="play_arrow").props("flat round").tooltip("Start embedded AI")
                )
                stop_button = ui.button(icon="stop").props("flat round").tooltip("Stop embedded AI")
                cancel_button = (
                    ui.button(icon="cancel").props("flat round").tooltip("Cancel current AI job")
                )
                refresh_button = (
                    ui.button(icon="refresh").props("flat round").tooltip("Refresh AI status")
                )

        progress_column = ui.column().classes("w-full gap-1 mt-3")
        with progress_column:
            progress_label = ui.label("").classes("text-[11px] text-[#edf5f7]")
            progress_bar = ui.linear_progress(value=0, show_value=False).classes("w-full")
            progress_detail = ui.label("").classes("th-muted")

        details_label = ui.label("").classes("th-muted mt-3")

    state: dict[str, Any] = {"status": initial, "active_job_id": None}

    def apply_status(status: dict[str, Any]) -> None:
        state["status"] = status
        runtime = status["runtime"]
        model = status["model"]
        server = status["server"]
        active_job = status.get("active_job")
        state["active_job_id"] = active_job.get("id") if active_job else None

        status_text = {
            "running": "● Ready",
            "external": "● External ready",
            "port_conflict": "Port conflict",
            "stopped": "Stopped",
        }.get(server["status"], str(server["status"]).title())
        status_label.set_text(status_text)
        details_label.set_text(
            f"Engine {'verified' if runtime['verified'] else 'not installed'} · "
            f"Model {'verified' if model['verified'] else 'not installed'} · "
            f"First download {_format_bytes(model['size_bytes'])}"
        )

        progress_column.set_visibility(bool(active_job))
        if active_job:
            completed = active_job.get("bytes_completed")
            total = active_job.get("total_bytes")
            percent = float(active_job.get("percent") or 0)
            progress_label.set_text(str(active_job.get("message") or "Working..."))
            progress_bar.value = max(0.0, min(1.0, percent / 100))
            if total:
                detail = (
                    f"{_format_bytes(completed)} / {_format_bytes(total)} · "
                    f"{percent:.1f}% · Job {active_job['id']}"
                )
            else:
                detail = f"{percent:.1f}% · Job {active_job['id']}"
            progress_detail.set_text(detail)
        controls = status["controls"]
        install_button.set_visibility(
            bool(controls["can_install"] and not (runtime["verified"] and model["verified"]))
        )
        start_button.set_visibility(bool(controls["can_start"]))
        stop_button.set_visibility(bool(controls["can_stop"]))
        cancel_button.set_visibility(bool(controls["can_cancel"]))
        editable_controls = (
            mode_toggle,
            autostart_switch,
            host_input,
            port_input,
            save_button,
        )
        for control in editable_controls:
            control.disable() if active_job else control.enable()
        status_timer.active = bool(active_job)

    def refresh_status() -> None:
        try:
            apply_status(_read_status())
        except Exception as exc:
            status_timer.active = False
            ui.notify(str(exc), type="negative")

    def configure_runtime() -> None:
        selected = str(mode_toggle.value or "standard")
        payload: dict[str, Any] = {
            "mode": selected,
            "autostart": bool(autostart_switch.value),
        }
        if selected == "external":
            payload.update(
                external_host=str(host_input.value or "127.0.0.1"),
                external_port=int(port_input.value or 1234),
            )
        result = dispatch_action(
            "ai.runtime.configure",
            payload,
            actor_type="ui",
            session_id=SESSION_ID,
        )
        if not result.success:
            ui.notify(result.error or "Local AI configuration failed.", type="negative")
            return
        ui.notify("Local AI configuration saved.", type="positive")
        external_row.set_visibility(selected == "external")
        refresh_status()

    def install_runtime() -> None:
        result = dispatch_action(
            "ai.runtime.install",
            {"acknowledge_download_gb": 2.1},
            actor_type="ui",
            session_id=SESSION_ID,
        )
        if not result.success:
            ui.notify(result.error or "Embedded AI installation did not start.", type="negative")
            return
        ui.notify(f"Installation started as job {result.data['job_id']}.", type="positive")
        status_timer.active = True
        refresh_status()

    def start_runtime() -> None:
        result = dispatch_action("ai.runtime.start", {}, actor_type="ui", session_id=SESSION_ID)
        if not result.success:
            ui.notify(result.error or "Embedded AI startup did not begin.", type="negative")
            return
        ui.notify("Embedded AI startup started.", type="positive")
        status_timer.active = True
        refresh_status()

    def stop_runtime() -> None:
        result = dispatch_action("ai.runtime.stop", {}, actor_type="ui", session_id=SESSION_ID)
        ui.notify(
            (result.data or {}).get("message") if result.success else result.error,
            type="positive" if result.success else "negative",
        )
        refresh_status()

    def cancel_runtime_job() -> None:
        job_id = state.get("active_job_id")
        if not job_id:
            return
        result = dispatch_action(
            "jobs.cancel",
            {"job_id": job_id},
            actor_type="ui",
            session_id=SESSION_ID,
        )
        ui.notify(
            "Embedded AI job cancelled." if result.success else result.error,
            type="positive" if result.success else "negative",
        )
        refresh_status()

    def mode_changed() -> None:
        selected = str(mode_toggle.value or "standard")
        external_row.set_visibility(selected == "external")
        if selected == "lite":
            mode_note.set_text("Lower context and CPU pressure for smaller computers.")
        elif selected == "standard":
            mode_note.set_text("Better context and Copilot accuracy on supported computers.")
        else:
            mode_note.set_text("Use a loopback LM Studio, Ollama, or custom compatible server.")

    mode_toggle.on_value_change(lambda _: mode_changed())
    save_button.on_click(configure_runtime)
    install_button.on_click(install_runtime)
    start_button.on_click(start_runtime)
    stop_button.on_click(stop_runtime)
    cancel_button.on_click(cancel_runtime_job)
    refresh_button.on_click(refresh_status)
    status_timer = ui.timer(3.0, refresh_status, active=False)
    apply_status(initial)
