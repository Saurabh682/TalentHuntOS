"""Connect Sites panel — log into LinkedIn/Naukri/etc and store encrypted cookies locally."""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Dict, Optional

from nicegui import ui


def render_connect_sites_panel(*, compact: bool = False) -> None:
    """Render platform connection cards (Settings or Communications)."""
    status_box = ui.column().classes("w-full gap-3")

    def refresh_status():
        from app.browser.session_auth import get_platform_connection_status

        rows = get_platform_connection_status()
        status_box.clear()
        with status_box:
            if not compact:
                ui.label(
                    "Connected only means cookies were saved. Click Test login to prove the "
                    "session works. If a site never opened Chromium, Disconnect → Connect again."
                ).classes("text-[11px] text-amber-300/90 mb-1")
            for row in rows:
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

            with ui.row().classes("items-center gap-1 flex-wrap"):
                if connectedish:
                    ui.button(
                        "Test login",
                        icon="fact_check",
                        on_click=lambda p=plat, l=label: _start_verify(p, l, on_changed),
                    ).props("flat dense").classes("text-xs text-teal-300")
                    ui.button(
                        "Reconnect",
                        icon="refresh",
                        on_click=lambda p=plat, l=label: _start_connect_dialog(p, l, on_changed),
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
                        on_click=lambda p=plat, l=label: _start_connect_dialog(p, l, on_changed),
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
                ui.label(f"Last used {row['last_accessed_at']}").classes("text-[11px] text-slate-500")
            if row.get("verify_detail") and status in {"invalid", "connected"}:
                ui.label(str(row["verify_detail"])).classes("text-[11px] text-slate-500")


def _disconnect(platform: str, on_changed) -> None:
    from app.browser.session_auth import disconnect_platform

    result = disconnect_platform(platform)
    if result.get("status") == "success":
        ui.notify(f"Disconnected {platform}", type="info")
    else:
        ui.notify("Disconnect failed", type="negative")
    on_changed()


def _start_verify(platform: str, label: str, on_changed) -> None:
    with ui.dialog() as dialog, ui.card().classes(
        "w-full max-w-md p-5 th-card border border-teal-500/40 gap-3"
    ):
        ui.label(f"Test {label} login").classes("text-lg font-bold text-slate-100")
        status_lbl = ui.label("Opening site with saved cookies…").classes("text-xs text-teal-300")
        ui.spinner(size="sm", color="teal")

        async def run_verify():
            from app.browser.session_auth import verify_platform_session

            result = await asyncio.to_thread(verify_platform_session, platform, headless=True)
            dialog.clear()
            with dialog, ui.card().classes(
                "w-full max-w-md p-5 th-card border border-teal-500/40 gap-3"
            ):
                if result.get("ok"):
                    ui.label(f"{label}: login works").classes("text-lg font-bold text-teal-300")
                    ui.label(result.get("detail") or "Verified").classes("text-xs text-slate-400")
                    if result.get("final_url"):
                        ui.label(result["final_url"]).classes("text-[11px] text-slate-500 break-all")
                    ui.notify(f"{label} verified", type="positive")
                else:
                    ui.label(f"{label}: not logged in").classes("text-lg font-bold text-orange-300")
                    ui.label(
                        result.get("error")
                        or "Saved cookies do not open an authenticated session."
                    ).classes("text-xs text-slate-300")
                    ui.label(
                        "Click Disconnect, then Connect, and sign in in the Chromium window that opens."
                    ).classes("text-[11px] text-amber-300")
                    ui.notify(result.get("error") or "Verification failed", type="warning")
                ui.button("Close", on_click=dialog.close).props("flat").classes(
                    "text-slate-400 text-xs self-end"
                )
                on_changed()

        ui.timer(0.05, run_verify, once=True)
    dialog.open()


def _start_connect_dialog(platform: str, label: str, on_changed) -> None:
    save_event = threading.Event()
    cancel_event = threading.Event()
    progress: Dict[str, Any] = {
        "message": "Opening a secure browser window…",
        "window_open": False,
        "login_page_loaded": False,
    }
    state: Dict[str, Optional[Any]] = {"result": None}

    with ui.dialog() as dialog, ui.card().classes(
        "w-full max-w-md p-5 th-card border border-teal-500/40 gap-3"
    ):
        ui.label(f"Connect {label}").classes("text-lg font-bold text-slate-100")
        ui.label(
            "1) Chromium opens → 2) Sign in fully until you see your home/feed → "
            "3) Then click Save session (or wait for auto-save). "
            "If you Save too early, the window stays open and nothing is stored."
        ).classes("text-xs text-slate-400")
        status_lbl = ui.label("Opening a secure browser window…").classes("text-xs text-teal-300")
        with ui.row().classes("w-full justify-end gap-2"):
            save_btn = ui.button(
                "Save session",
                icon="save",
                on_click=lambda: save_event.set(),
            ).props("flat dense").classes("text-xs text-teal-300")
            save_btn.disable()

            def do_cancel():
                cancel_event.set()
                dialog.close()

            ui.button("Cancel", on_click=do_cancel).props("flat").classes("text-slate-400 text-xs")

        def _poll_progress():
            msg = progress.get("message")
            if msg:
                status_lbl.set_text(str(msg))
            if progress.get("login_page_loaded"):
                save_btn.enable()

        progress_timer = ui.timer(0.5, _poll_progress)

        async def run_connect():
            from app.browser.session_auth import interactive_connect

            status_lbl.set_text(f"Opening a browser for {label}…")

            def _work():
                return interactive_connect(
                    platform,
                    timeout_sec=600,
                    save_event=save_event,
                    cancel_event=cancel_event,
                    progress=progress,
                )

            result = await asyncio.to_thread(_work)
            state["result"] = result
            try:
                progress_timer.deactivate()
            except Exception:
                pass
            if result.get("status") == "success" and result.get("verified"):
                status_lbl.set_text(
                    f"Verified · {result.get('cookie_count', 0)} cookies encrypted"
                )
                ui.notify(f"{label} verified and connected", type="positive")
                dialog.close()
                on_changed()
            elif result.get("status") == "success":
                # Should not happen with new flow — treat as incomplete
                status_lbl.set_text("Saved but not verified — use Test login or Reconnect")
                ui.notify(f"{label} saved without verify — run Test login", type="warning")
                dialog.close()
                on_changed()
            elif result.get("status") == "cancelled":
                status_lbl.set_text("Cancelled")
            else:
                status_lbl.set_text(result.get("error") or "Failed")
                ui.notify(result.get("error") or "Connect failed", type="warning")

        ui.timer(0.05, run_connect, once=True)

    dialog.open()
