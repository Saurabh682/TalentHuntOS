"""Three-panel layout for TalentHunt OS — Modern Ocean design pack."""

from nicegui import ui

from app.ui.panels.copilot_panel import render_copilot_panel
from app.ui.theme import apply_theme


def _ai_engine_label() -> tuple[str, str]:
    """Return a truthful, non-secret sidebar summary of local AI readiness."""
    try:
        from app.ai.embedded_runtime import public_status

        status = public_status()
        server = status["server"]["status"]
        if not status["runtime"]["verified"] or not status["model"]["verified"]:
            return "Setup required", "#f5b942"
        if server == "running":
            return "Local Ready", "#19d3c5"
        if server == "external":
            return "External Ready", "#19d3c5"
        if server == "port_conflict":
            return "Port in use", "#f5b942"
        return "Local stopped", "#8ea4b4"
    except Exception:
        return "Status unavailable", "#8ea4b4"


def create_layout(main_content_fn, active_path: str = "/"):
    """Render the standard 3-panel shell layout matching the Modern HTML UI.

    Panel 1 (Left): Navigation Sidebar
    Panel 2 (Center): Main Content Area
    Panel 3 (Right): Copilot Chat & Voice Panel
    """
    apply_theme()
    ai_label, ai_color = _ai_engine_label()

    current_path = active_path
    try:
        if hasattr(ui.context, "client") and ui.context.client and ui.context.client.page:
            current_path = ui.context.client.page.path
    except Exception:
        pass

    with ui.element("div").classes("th-shell"):
        # Panel 1: Left Navigation Sidebar
        with (
            ui.element("aside")
            .classes("th-sidebar")
            .style(
                "width:220px;padding:22px 15px;background:#08121d;"
                "border-right:1px solid #1b3040;display:flex;flex-direction:column;"
                "justify-content:space-between;overflow-y:auto;flex-shrink:0;"
            )
        ):
            with ui.element("div"):
                with ui.element("div").style("padding:8px 10px 28px"):
                    ui.label("TalentHunt OS").classes("text-[15px] font-extrabold text-[#edf5f7]")
                    ui.label("AI Recruiter Copilot").classes(
                        "text-[11px] font-medium text-[#19d3c5]"
                    ).style("margin-top:4px")

                nav_items = [
                    ("Dashboard", "dashboard", "/"),
                    ("Hunts", "travel_explore", "/hunts"),
                    ("Discoveries", "person_search", "/discoveries"),
                    ("Candidates", "group", "/candidates"),
                    ("Pipeline", "view_kanban", "/pipeline"),
                    ("Playbook", "menu_book", "/playbook"),
                    ("Communications", "forum", "/communications"),
                    ("Analytics", "insights", "/analytics"),
                    ("Settings", "settings", "/settings"),
                ]

                for label, icon, path in nav_items:
                    is_active = current_path == path or (
                        path != "/" and current_path.startswith(path)
                    )
                    bg = "background:#123542;color:#fff;" if is_active else "color:#8ea4b4;"
                    with (
                        ui.element("div")
                        .style(
                            f"display:flex;align-items:center;gap:12px;padding:11px 13px;"
                            f"border-radius:9px;margin:3px 0;cursor:pointer;{bg}"
                        )
                        .on("click", lambda p=path: ui.navigate.to(p))
                    ):
                        ui.icon(icon, size="18px").style("color:inherit")
                        ui.label(label).style("font-size:13px;color:inherit")

            with ui.column().classes("w-full gap-2"):
                with (
                    ui.element("div")
                    .classes("th-engine")
                    .style(
                        "display:flex;align-items:center;justify-content:space-between;width:100%"
                    )
                ):
                    ui.label("AI Engine").style("font-size:11px;color:#8296a7")
                    ui.label(ai_label).style(f"font-size:11px;color:{ai_color};font-weight:600")
                ui.button(
                    "Sign out",
                    icon="logout",
                    on_click=lambda: ui.run_javascript("window.location.href='/auth/logout'"),
                ).props("flat dense no-caps").classes("w-full text-xs text-slate-400")

        # Panel 2: Center Main Content
        with ui.element("main").classes("th-main"):
            main_content_fn()

        # Panel 3: Right Copilot
        with (
            ui.element("aside")
            .classes("th-copilot-panel")
            .style(
                "width:320px;padding:16px;background:#08121d;"
                "border-left:1px solid #1b3040;display:flex;flex-direction:column;"
                "overflow:hidden;flex-shrink:0;"
            )
        ):
            render_copilot_panel()

        with ui.element("nav").classes("th-mobile-nav"):
            mobile_items = [
                ("dashboard", "/", "Dashboard"),
                ("travel_explore", "/hunts", "Hunts"),
                ("person_search", "/discoveries", "Discoveries"),
                ("group", "/candidates", "Candidates"),
                ("view_kanban", "/pipeline", "Pipeline"),
                ("menu_book", "/playbook", "Playbook"),
                ("forum", "/communications", "Communications"),
                ("insights", "/analytics", "Analytics"),
                ("settings", "/settings", "Settings"),
            ]
            for icon, path, label in mobile_items:
                ui.button(
                    icon=icon,
                    on_click=lambda p=path: ui.navigate.to(p),
                ).props("flat round dense").tooltip(label)
            ui.button(
                icon="smart_toy",
                on_click=lambda: ui.run_javascript(
                    "document.querySelector('.th-copilot-panel')?.classList.toggle('th-mobile-open')"
                ),
            ).props("flat round dense").classes("text-[#19d3c5]").tooltip("Copilot")
