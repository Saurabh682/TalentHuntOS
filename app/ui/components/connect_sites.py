"""Connect Sites panel — log into LinkedIn/Naukri/etc and store encrypted cookies locally."""

from __future__ import annotations

from typing import Any, Dict

from nicegui import ui


def render_connect_sites_panel(*, compact: bool = False) -> None:
    """Render platform connection cards (Settings or Communications)."""
    status_box = ui.column().classes("w-full gap-3")

    def refresh_status():
        from app.actions.api import dispatch_action

        result = dispatch_action(
            "sites.list",
            {},
            actor_type="ui",
            session_id="settings-connected-sites",
        )
        status_box.clear()
        with status_box:
            if not result.success:
                ui.label(result.error or "Connected sites could not be loaded.").classes(
                    "text-sm text-red-300"
                )
                return
            if not compact:
                ui.label(
                    "Saved sessions are encrypted locally. Test login proves a session still "
                    "works; passwords and cookie values are never shown or stored in action logs."
                ).classes("text-[11px] text-amber-300/90 mb-1")
            for row in result.data.get("sites", []):
                _render_platform_row(row, on_changed=refresh_status, compact=compact)

    refresh_status()


def _render_platform_row(
    row: Dict[str, Any],
    *,
    on_changed,
    compact: bool = False,
) -> None:
    plat = row["platform"]
    label = row["label"]
    status = row.get("status") or "disconnected"
    encrypted = bool(row.get("encrypted"))
    connectedish = status in {"connected", "verified", "invalid"}
    active_job = row.get("active_job") or None

    border = {
        "verified": "border-teal-500/40",
        "connected": "border-amber-500/40",
        "invalid": "border-orange-500/50",
        "disconnected": "border-slate-700/50",
    }.get(status, "border-slate-700/50")

    with ui.card().classes(f"w-full p-4 th-card border gap-2 {border}"):
        with ui.row().classes("w-full items-center justify-between gap-2 flex-wrap"):
            with ui.row().classes("items-center gap-2 flex-wrap"):
                icon_name = {
                    "verified": "verified_user",
                    "connected": "hourglass_top",
                    "invalid": "warning",
                    "disconnected": "link_off",
                }.get(status, "link_off")
                icon_color = {
                    "verified": "teal-4",
                    "connected": "amber-4",
                    "invalid": "orange-4",
                    "disconnected": "slate-5",
                }.get(status, "slate-5")
                ui.icon(icon_name, color=icon_color, size="sm")
                ui.label(label).classes("text-sm font-semibold text-slate-100")

                if status == "verified":
                    ui.badge("Verified login", color="teal").classes("text-[10px]")
                elif status == "connected":
                    ui.badge("Saved · not verified", color="amber").classes("text-[10px]")
                elif status == "invalid":
                    ui.badge("Not a real login", color="orange").classes("text-[10px]")
                else:
                    ui.badge("Not connected", color="blue-grey").classes("text-[10px]")

                if connectedish and encrypted:
                    ui.badge("Encrypted", color="indigo").classes("text-[10px]")
                if active_job:
                    working_label = (
                        "Connecting" if active_job.get("kind") == "site_connect" else "Verifying"
                    )
                    ui.badge(working_label, color="blue").classes("text-[10px]")

            with ui.row().classes("items-center gap-1 flex-wrap"):
                if active_job:
                    ui.button(
                        "Cancel",
                        icon="stop",
                        on_click=lambda jid=active_job["id"]: _cancel_site_job(jid, on_changed),
                    ).props("flat dense").classes("text-xs text-amber-300")
                elif connectedish:
                    ui.button(
                        "Test login",
                        icon="fact_check",
                        on_click=lambda p=plat, site_label=label: _start_verify(
                            p, site_label, on_changed
                        ),
                    ).props("flat dense").classes("text-xs text-teal-300")
                    ui.button(
                        "Reconnect",
                        icon="refresh",
                        on_click=lambda p=plat, site_label=label: _start_connect_dialog(
                            p, site_label, on_changed, reconnect=True
                        ),
                    ).props("flat dense").classes("text-xs text-slate-300")
                    ui.button(
                        "Disconnect",
                        icon="logout",
                        on_click=lambda p=plat: _disconnect(p, on_changed),
                    ).props("flat dense").classes("text-xs text-slate-400")
                else:
                    ui.button(
                        "Connect",
                        icon="login",
                        on_click=lambda p=plat, site_label=label: _start_connect_dialog(
                            p, site_label, on_changed, reconnect=False
                        ),
                    ).classes("th-primary-btn text-xs")

        if not compact:
            if status == "invalid":
                ui.label(
                    "Cookies were saved without a real sign-in. Disconnect, then Connect — "
                    "a Chromium window must open so you can log in."
                ).classes("text-[11px] text-orange-300")
            elif status == "connected":
                ui.label(
                    "Cookies are stored but not proven. Click Test login (opens the site headless)."
                ).classes("text-[11px] text-amber-300/90")
            elif status == "verified" and row.get("verified_at"):
                ui.label(f"Verified {row['verified_at']}").classes("text-[11px] text-slate-500")
            elif status == "disconnected":
                ui.label(
                    f"Opens a real Chromium window so you can sign in to {label}. "
                    "Cookies are encrypted on this PC only — no passwords saved."
                ).classes("text-[11px] text-slate-500")
            if row.get("last_accessed_at") and status != "disconnected":
                ui.label(f"Last used {row['last_accessed_at']}").classes(
                    "text-[11px] text-slate-500"
                )
            if row.get("verify_detail") and status in {"invalid", "connected"}:
                ui.label(str(row["verify_detail"])).classes("text-[11px] text-slate-500")
            if active_job:
                ui.label(
                    f"Job #{active_job['id']} · {active_job.get('message') or 'Working...'}"
                ).classes("text-[11px] text-sky-300")


def _cancel_site_job(job_id: str, on_changed) -> None:
    from app.actions.api import dispatch_action

    result = dispatch_action(
        "jobs.cancel",
        {"job_id": job_id},
        actor_type="ui",
        session_id="settings-connected-sites",
    )
    ui.notify(
        ((result.data or {}).get("message") if result.success else result.error)
        or "Cancellation failed.",
        type="info" if result.success else "negative",
    )
    on_changed()


def _disconnect(platform: str, on_changed) -> None:
    from app.actions.api import (
        approve_and_dispatch,
        cancel_approval,
        dispatch_preview,
    )

    approval_session = f"settings-site-{platform}"
    requested = dispatch_preview(
        "sites.disconnect",
        {"platform": platform},
        actor_type="ui",
        session_id=approval_session,
    )
    if not requested.success:
        ui.notify(requested.error or "Disconnect preview failed.", type="negative")
        return
    pending = requested.data or {}
    preview = pending.get("preview") or {}

    with (
        ui.dialog() as dialog,
        ui.card().classes("w-full max-w-md p-5 th-card border border-orange-500/40 gap-3"),
    ):
        ui.label(preview.get("title") or "Disconnect site").classes(
            "text-lg font-bold text-slate-100"
        )
        ui.label(preview.get("summary") or "Deactivate the saved browser session.").classes(
            "text-sm text-slate-300"
        )
        ui.label("Undo remains available for seven days.").classes("text-xs text-amber-300")
        with ui.row().classes("w-full justify-end gap-2"):

            def cancel_disconnect():
                cancel_approval(
                    int(pending["approval_id"]),
                    session_id=approval_session,
                )
                dialog.close()

            def confirm_disconnect():
                result = approve_and_dispatch(
                    int(pending["approval_id"]),
                    session_id=approval_session,
                    actor_type="ui",
                )
                ui.notify(
                    ((result.data or {}).get("message") if result.success else result.error)
                    or "Disconnect failed.",
                    type="info" if result.success else "negative",
                )
                if result.success:
                    dialog.close()
                    on_changed()

            ui.button("Cancel", on_click=cancel_disconnect).props("flat no-caps")
            ui.button(
                "Disconnect",
                icon="logout",
                on_click=confirm_disconnect,
            ).props("color=orange no-caps")
    dialog.open()


def _start_verify(platform: str, label: str, on_changed) -> None:
    from app.actions.api import dispatch_action

    started = dispatch_action(
        "sites.verify",
        {"platform": platform},
        actor_type="ui",
        session_id="settings-connected-sites",
    )
    if not started.success:
        ui.notify(started.error or "Login verification could not start.", type="negative")
        return
    job_id = str((started.data or {}).get("job_id") or "")
    timer_ref: Dict[str, Any] = {"timer": None}

    with (
        ui.dialog() as dialog,
        ui.card().classes("w-full max-w-md p-5 th-card border border-teal-500/40 gap-3"),
    ):
        ui.label(f"Test {label} login").classes("text-lg font-bold text-slate-100")
        ui.label(f"Background job #{job_id}").classes("text-[10px] text-slate-500")
        status_lbl = ui.label((started.data or {}).get("message") or "Starting...").classes(
            "text-xs text-teal-300"
        )
        ui.spinner(size="sm", color="teal")

        def poll_verify():
            result = dispatch_action(
                "jobs.get",
                {"job_id": job_id},
                actor_type="ui",
                session_id="settings-connected-sites",
            )
            if not result.success:
                status_lbl.set_text(result.error or "Verification status is unavailable.")
                return
            job = (result.data or {}).get("job") or {}
            status_lbl.set_text(job.get("message") or "Verifying...")
            if job.get("status") == "running":
                return
            timer = timer_ref.get("timer")
            if timer:
                timer.deactivate()
            message = str(job.get("message") or "Verification finished.")
            verified = job.get("status") == "done" and "login is verified" in message.lower()
            ui.notify(
                message,
                type="positive"
                if verified
                else ("info" if job.get("status") == "cancelled" else "warning"),
            )
            dialog.close()
            on_changed()

        timer_ref["timer"] = ui.timer(0.6, poll_verify)
    dialog.open()


def _start_connect_dialog(
    platform: str,
    label: str,
    on_changed,
    *,
    reconnect: bool,
) -> None:
    from app.actions.api import dispatch_action

    action_name = "sites.reconnect" if reconnect else "sites.connect"
    started = dispatch_action(
        action_name,
        {"platform": platform},
        actor_type="ui",
        session_id="settings-connected-sites",
    )
    if not started.success:
        ui.notify(started.error or f"{label} login could not start.", type="negative")
        return
    job_id = str((started.data or {}).get("job_id") or "")
    timer_ref: Dict[str, Any] = {"timer": None}

    with (
        ui.dialog() as dialog,
        ui.card().classes("w-full max-w-md p-5 th-card border border-teal-500/40 gap-3"),
    ):
        ui.label(f"{'Reconnect' if reconnect else 'Connect'} {label}").classes(
            "text-lg font-bold text-slate-100"
        )
        ui.label(
            "A visible browser opens for you to sign in directly. Copilot stays available. "
            "The session auto-saves only after the site confirms you are logged in."
        ).classes("text-xs text-slate-400")
        ui.label(f"Background job #{job_id}").classes("text-[10px] text-slate-500")
        status_lbl = ui.label((started.data or {}).get("message") or "Starting...").classes(
            "text-xs text-teal-300"
        )

        def request_save():
            result = dispatch_action(
                "sites.connect.save",
                {"job_id": job_id},
                actor_type="ui",
                session_id="settings-connected-sites",
            )
            status_lbl.set_text(
                ((result.data or {}).get("message") if result.success else result.error)
                or "Save request failed."
            )
            if not result.success:
                ui.notify(result.error or "Save request failed.", type="negative")

        def do_cancel():
            result = dispatch_action(
                "jobs.cancel",
                {"job_id": job_id},
                actor_type="ui",
                session_id="settings-connected-sites",
            )
            ui.notify(
                ((result.data or {}).get("message") if result.success else result.error)
                or "Cancellation failed.",
                type="info" if result.success else "negative",
            )
            timer = timer_ref.get("timer")
            if timer:
                timer.deactivate()
            dialog.close()
            on_changed()

        with ui.row().classes("w-full justify-end gap-2"):
            save_btn = (
                ui.button("Save session", icon="save", on_click=request_save)
                .props("flat dense no-caps")
                .classes("text-xs text-teal-300")
            )
            save_btn.disable()
            ui.button("Cancel", on_click=do_cancel).props("flat no-caps").classes(
                "text-slate-400 text-xs"
            )

        def poll_connection():
            result = dispatch_action(
                "jobs.get",
                {"job_id": job_id},
                actor_type="ui",
                session_id="settings-connected-sites",
            )
            if not result.success:
                status_lbl.set_text(result.error or "Connection status is unavailable.")
                return
            job = (result.data or {}).get("job") or {}
            status_lbl.set_text(job.get("message") or "Waiting for login...")
            if job.get("ready_for_save"):
                save_btn.enable()
            else:
                save_btn.disable()
            if job.get("status") == "running":
                return
            timer = timer_ref.get("timer")
            if timer:
                timer.deactivate()
            message = str(job.get("message") or "Connection finished.")
            ui.notify(
                message,
                type=(
                    "positive"
                    if job.get("status") == "done"
                    else ("info" if job.get("status") == "cancelled" else "warning")
                ),
            )
            dialog.close()
            on_changed()

        timer_ref["timer"] = ui.timer(0.5, poll_connection)

    dialog.open()
