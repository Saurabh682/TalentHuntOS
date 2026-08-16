"""NiceGUI Communications Hub Page (Outreach Logs, Email Templates, Drip Sequences, & Embedded Browser)."""

from nicegui import ui

from app.actions.api import dispatch_action, dispatch_preview
from app.candidates.models import Candidate
from app.candidates.service import list_candidates
from app.communications.models import MessageTemplate
from app.communications.outreach_service import (
    list_sequences,
    seed_default_sequence_if_empty,
)
from app.communications.service import (
    list_communications,
    list_templates,
    seed_default_templates_if_empty,
)
from app.communications.template_engine import generate_candidate_outreach
from app.infrastructure.db import SessionFactory, init_db
from app.ui.layout import create_layout
from app.ui.panels.browser_panel import render_browser_panel


def render_communications():
    """Render the Communications Hub page content."""
    init_db()
    with SessionFactory() as db:
        seed_default_templates_if_empty(db)
        seed_default_sequence_if_empty(db)

    selected_channel_filter = {"value": "All"}
    try:
        from app.communications.email_service import get_delivery_account_summary

        email_account = get_delivery_account_summary()
    except Exception:
        email_account = {"configured": False, "email_address": None}

    with ui.column().classes("w-full gap-0"):
        # Page Title Header
        with ui.row().classes("w-full justify-between items-center gap-5 mb-[22px]"):
            with ui.column().classes("gap-0"):
                ui.label("Outreach engine").classes("th-ey")
                ui.label("Communication Hub").classes("th-title")
                ui.label(
                    "Multi-channel candidate messaging, templates and automated sequences."
                ).classes("th-muted")

            with ui.row().classes("items-center gap-3"):
                ui.badge(
                    email_account.get("email_address")
                    if email_account.get("configured")
                    else "Email not configured",
                    color="teal" if email_account.get("configured") else "blue-grey",
                ).classes("text-[10px]").style(
                    "background:#344954!important;color:#fff!important"
                    if not email_account.get("configured")
                    else ""
                )
                ui.button(
                    "Review Due Outreach", icon="fact_check", on_click=lambda: run_drip_engine()
                ).classes("th-amber-btn")

                ui.button(
                    "Send Email",
                    icon="send",
                    on_click=lambda: open_send_email_dialog(),
                ).classes("th-primary-btn")

                ui.button(
                    "Log Communication",
                    icon="add_comment",
                    on_click=lambda: open_log_communication_dialog(),
                ).classes("th-primary-btn")

        # Navigation Tabs for Sections
        with ui.tabs().classes("w-full text-[#19d3c5] border-b border-[#1b3040]") as comm_tabs:
            tab_logs = ui.tab("Communication Logs", icon="forum")
            tab_templates = ui.tab("Message Templates", icon="description")
            tab_sequences = ui.tab("Outreach Sequences (Drip)", icon="auto_mode")
            tab_browser = ui.tab("Embedded Sourcing Browser", icon="language")

        with ui.tab_panels(comm_tabs, value=tab_logs).classes("w-full bg-transparent p-0"):
            # --- TAB 1: COMMUNICATION LOGS ---
            with ui.tab_panel(tab_logs).classes("w-full p-0 gap-4 column"):
                with ui.card().classes("w-full p-4 th-card border border-teal-900/30 gap-4"):
                    with ui.row().classes("w-full justify-between items-center flex-wrap gap-3"):
                        with ui.row().classes("items-center gap-2"):
                            ui.label("Filter Channel:").classes(
                                "text-xs font-semibold text-teal-400"
                            )
                            for ch in ["All", "email", "linkedin", "naukri", "whatsapp", "phone"]:
                                ui.button(
                                    ch.upper() if len(ch) <= 5 else ch.title(),
                                    on_click=lambda e, c=ch: set_log_filter(c),
                                ).props("dense flat").classes(
                                    "text-xs px-2.5 py-1 rounded-full bg-slate-800 text-slate-300 hover:text-teal-400"
                                )

                        pass

                logs_container = ui.column().classes("w-full gap-3")
                refresh_logs_ref = {"fn": lambda: None}

                def set_log_filter(ch: str):
                    selected_channel_filter["value"] = ch
                    refresh_logs_ref["fn"]()

                def refresh_logs():
                    logs_container.clear()
                    with logs_container:
                        with SessionFactory() as db:
                            logs = list_communications(db, channel=selected_channel_filter["value"])

                            if not logs:
                                with ui.card().classes(
                                    "w-full p-10 th-card items-center justify-center text-center gap-2"
                                ):
                                    ui.icon("mark_email_unread", size="xl", color="blue-grey")
                                    ui.label(
                                        "No communication records found for this filter."
                                    ).classes("text-slate-400")
                                return

                            for log in logs:
                                ch_icon = {
                                    "email": "email",
                                    "linkedin": "work",
                                    "naukri": "business_center",
                                    "whatsapp": "chat",
                                    "phone": "phone",
                                }.get((log.channel or "unknown").lower(), "message")

                                icon_color = {
                                    "email": "indigo-4",
                                    "linkedin": "blue-4",
                                    "naukri": "amber-4",
                                    "whatsapp": "emerald-4",
                                    "phone": "teal-4",
                                }.get((log.channel or "unknown").lower(), "teal-4")

                                dir_color = "teal" if log.direction == "outbound" else "indigo"

                                with ui.card().classes(
                                    "w-full p-4 th-card border border-teal-900/30 hover:border-teal-500/30 transition-all gap-2"
                                ):
                                    with ui.row().classes(
                                        "w-full justify-between items-center flex-wrap gap-2"
                                    ):
                                        with ui.row().classes("items-center gap-3"):
                                            ui.icon(ch_icon, color=icon_color, size="md")
                                            with ui.column().classes("gap-0"):
                                                with ui.row().classes("items-center gap-2"):
                                                    ui.label(
                                                        log.subject
                                                        or f"{log.channel.title()} Message"
                                                    ).classes("text-base font-bold text-slate-100")
                                                    ui.badge(
                                                        (log.direction or "unknown").upper(),
                                                        color=dir_color,
                                                    ).classes("text-[9px] px-1.5 py-0.5")
                                                    ui.badge(
                                                        (log.channel or "unknown").upper(),
                                                        color="blue-grey",
                                                    ).classes(
                                                        "text-[9px] text-teal-300 px-1.5 py-0.5 border border-teal-900/40"
                                                    ).style(
                                                        "background:#344954!important;color:#a7f3e8!important"
                                                    )

                                                ui.label(
                                                    f"From: {log.sender}  ➜  To: {log.recipient}"
                                                ).classes("text-xs text-slate-400")

                                        with ui.column().classes("items-end gap-0"):
                                            ui.label(
                                                log.created_at.strftime("%Y-%m-%d %H:%M")
                                                if log.created_at
                                                else ""
                                            ).classes("text-[11px] text-slate-500")
                                            st_color = (
                                                "teal"
                                                if log.status in ["sent", "received", "read"]
                                                else "red"
                                            )
                                            ui.badge(log.status.title(), color=st_color).classes(
                                                "text-[10px]"
                                            )

                                    ui.separator().classes("bg-teal-900/20 my-1")
                                    ui.markdown(log.body).classes(
                                        "text-xs text-slate-300 leading-relaxed px-1"
                                    )

                refresh_logs_ref["fn"] = refresh_logs
                refresh_logs()

            # --- TAB 2: MESSAGE TEMPLATES & TESTER ---
            with ui.tab_panel(tab_templates).classes("w-full p-0 gap-4 column"):
                with ui.row().classes("w-full justify-between items-center"):
                    ui.label("Outreach Templates & Merge Variables").classes(
                        "text-lg font-bold text-slate-100"
                    )
                    ui.button(
                        "Create Template",
                        icon="add",
                        color="teal",
                        on_click=lambda: open_create_template_dialog(),
                    ).classes("th-teal-btn text-xs")

                templates_container = ui.column().classes("w-full gap-4")

                def refresh_templates():
                    templates_container.clear()
                    with templates_container:
                        with SessionFactory() as db:
                            tmpls = list_templates(db)

                            for tmpl in tmpls:
                                tid = tmpl.id
                                with ui.card().classes(
                                    "w-full p-5 th-card border border-teal-900/30 gap-3"
                                ):
                                    with ui.row().classes(
                                        "w-full justify-between items-center flex-wrap gap-2"
                                    ):
                                        with ui.row().classes("items-center gap-3"):
                                            ui.icon("description", color="teal-4", size="md")
                                            with ui.column().classes("gap-0"):
                                                with ui.row().classes("items-center gap-2"):
                                                    ui.label(tmpl.name).classes(
                                                        "text-base font-bold text-slate-100"
                                                    )
                                                    ui.badge(
                                                        tmpl.channel.upper(), color="teal"
                                                    ).classes("text-[10px]")
                                                    if tmpl.category:
                                                        ui.badge(
                                                            tmpl.category, color="indigo-9"
                                                        ).classes("text-[10px]")
                                                if tmpl.subject:
                                                    ui.label(f"Subject: {tmpl.subject}").classes(
                                                        "text-xs text-teal-300 font-medium"
                                                    )

                                        with ui.row().classes("items-center gap-2"):
                                            ui.button(
                                                "Test Personalization",
                                                icon="auto_fix_high",
                                                on_click=lambda e, t=tmpl: (
                                                    open_template_tester_dialog(t)
                                                ),
                                            ).props("dense flat").classes(
                                                "text-xs text-indigo-300 bg-indigo-950/60 border border-indigo-500/30 px-2.5 py-1 rounded"
                                            )

                                            ui.button(
                                                icon="delete_outline",
                                                on_click=lambda e, t_id=tid: do_archive_template(
                                                    t_id
                                                ),
                                            ).props("flat round dense").classes(
                                                "text-slate-500 hover:text-red-400"
                                            )

                                    ui.separator().classes("bg-teal-900/20 my-1")
                                    ui.code(tmpl.body_template).classes(
                                        "w-full p-3 bg-slate-950 text-xs text-slate-300 font-mono rounded"
                                    )

                def do_archive_template(tid: int):
                    result = dispatch_action(
                        "communications.templates.active.set",
                        {"template_id": tid, "is_active": False},
                        actor_type="ui",
                        session_id="ui:communications",
                    )
                    if not result.success:
                        ui.notify(
                            result.error or "Template could not be archived.", type="negative"
                        )
                        return
                    ui.notify(
                        "Template archived. You can undo this from Action History.", type="info"
                    )
                    refresh_templates()

                refresh_templates()

            # --- TAB 3: OUTREACH SEQUENCES (DRIP CAMPAIGNS) ---
            with ui.tab_panel(tab_sequences).classes("w-full p-0 gap-4 column"):
                with ui.row().classes("w-full justify-between items-center"):
                    ui.label("Drip Outreach Campaign Sequences").classes(
                        "text-lg font-bold text-slate-100"
                    )
                    with ui.row().classes("items-center gap-2"):
                        ui.button(
                            "Enroll Candidate",
                            icon="person_add",
                            color="teal",
                            on_click=lambda: open_enroll_dialog(),
                        ).classes("th-teal-btn text-xs")
                        ui.button(
                            "Create Sequence",
                            icon="playlist_add",
                            on_click=lambda: open_create_sequence_dialog(),
                        ).props("dense flat").classes(
                            "text-xs text-teal-300 border border-teal-500/30 px-3 py-1.5 rounded"
                        )

                sequences_container = ui.column().classes("w-full gap-4")

                def refresh_sequences():
                    sequences_container.clear()
                    with sequences_container:
                        with SessionFactory() as db:
                            seqs = list_sequences(db)

                            for seq in seqs:
                                with ui.card().classes(
                                    "w-full p-5 th-card border border-teal-900/30 gap-4"
                                ):
                                    with ui.row().classes(
                                        "w-full justify-between items-center flex-wrap gap-2"
                                    ):
                                        with ui.row().classes("items-center gap-3"):
                                            ui.icon("auto_mode", color="amber-4", size="md")
                                            with ui.column().classes("gap-0"):
                                                ui.label(seq.name).classes(
                                                    "text-lg font-bold text-slate-100"
                                                )
                                                ui.label(
                                                    seq.description or "No description"
                                                ).classes("text-xs text-slate-400")

                                        with ui.row().classes("items-center gap-3"):
                                            ui.badge(
                                                "ACTIVE" if seq.is_active else "PAUSED",
                                                color="teal" if seq.is_active else "blue-grey",
                                            ).classes("text-[10px]")
                                            ui.badge(
                                                f"{len(seq.steps)} Steps", color="teal"
                                            ).classes("text-xs font-bold")
                                            ui.badge(
                                                f"{len(seq.enrollments)} Enrolled Candidates",
                                                color="indigo",
                                            ).classes("text-xs font-bold")
                                            ui.button(
                                                icon="pause" if seq.is_active else "play_arrow",
                                                on_click=lambda e, sid=seq.id, active=seq.is_active: (
                                                    do_set_sequence_active(sid, not active)
                                                ),
                                            ).props("flat round dense").tooltip(
                                                "Pause sequence"
                                                if seq.is_active
                                                else "Restore sequence"
                                            )

                                    ui.separator().classes("bg-teal-900/20 my-1")

                                    # Render sequence steps visually
                                    ui.label("Campaign Steps Timeline:").classes(
                                        "text-xs font-semibold text-teal-400"
                                    )
                                    with ui.row().classes("w-full gap-3 items-center flex-wrap"):
                                        for idx, st in enumerate(seq.steps):
                                            with ui.card().classes(
                                                "p-3 bg-slate-950 border border-teal-900/40 rounded-lg gap-1 min-w-[200px]"
                                            ):
                                                with ui.row().classes(
                                                    "justify-between items-center w-full"
                                                ):
                                                    ui.badge(
                                                        f"Step {st.step_number}", color="teal-9"
                                                    ).classes("text-[10px]")
                                                    ui.label(
                                                        f"Delay: {st.delay_days} days"
                                                    ).classes(
                                                        "text-[10px] text-amber-400 font-medium"
                                                    )
                                                ui.label(st.subject or "Outreach Email").classes(
                                                    "text-xs font-semibold text-slate-200 line-clamp-1"
                                                )
                                                ui.label(
                                                    st.body_override[:60] + "..."
                                                    if st.body_override
                                                    else "Template message"
                                                ).classes("text-[11px] text-slate-400 line-clamp-2")

                                            if idx < len(seq.steps) - 1:
                                                ui.icon("arrow_forward", color="teal-4", size="sm")

                                    if seq.enrollments:
                                        ui.label("Enrollments").classes(
                                            "text-xs font-semibold text-teal-400 mt-1"
                                        )
                                        with ui.column().classes("w-full gap-1"):
                                            for enrollment in seq.enrollments:
                                                with ui.row().classes(
                                                    "w-full items-center justify-between border-t border-teal-900/20 py-2"
                                                ):
                                                    with ui.column().classes("gap-0"):
                                                        ui.label(
                                                            enrollment.candidate.full_name
                                                            if enrollment.candidate
                                                            else f"Candidate #{enrollment.candidate_id}"
                                                        ).classes("text-xs text-slate-200")
                                                        ui.label(
                                                            f"Step {enrollment.current_step_number} · {enrollment.status.title()}"
                                                        ).classes("text-[10px] text-slate-500")
                                                    if enrollment.status in {"active", "paused"}:
                                                        next_status = (
                                                            "paused"
                                                            if enrollment.status == "active"
                                                            else "active"
                                                        )
                                                        ui.button(
                                                            icon="pause"
                                                            if next_status == "paused"
                                                            else "play_arrow",
                                                            on_click=lambda e, eid=enrollment.id, status=next_status: (
                                                                do_set_enrollment_status(
                                                                    eid, status
                                                                )
                                                            ),
                                                        ).props("flat round dense").tooltip(
                                                            "Pause enrollment"
                                                            if next_status == "paused"
                                                            else "Resume enrollment"
                                                        )

                def do_set_sequence_active(sequence_id: int, is_active: bool):
                    result = dispatch_action(
                        "communications.sequences.active.set",
                        {"sequence_id": sequence_id, "is_active": is_active},
                        actor_type="ui",
                        session_id="ui:communications",
                    )
                    if not result.success:
                        ui.notify(result.error or "Sequence could not be updated.", type="negative")
                        return
                    ui.notify(
                        "Sequence updated. Undo is available in Action History.", type="positive"
                    )
                    refresh_sequences()

                def do_set_enrollment_status(enrollment_id: int, status: str):
                    result = dispatch_action(
                        "communications.enrollments.status.set",
                        {"enrollment_id": enrollment_id, "status": status},
                        actor_type="ui",
                        session_id="ui:communications",
                    )
                    if not result.success:
                        ui.notify(
                            result.error or "Enrollment could not be updated.", type="negative"
                        )
                        return
                    ui.notify(
                        f"Enrollment {status}. Undo is available in Action History.",
                        type="positive",
                    )
                    refresh_sequences()

                refresh_sequences()

            # --- TAB 4: EMBEDDED SOURCING BROWSER ---
            with ui.tab_panel(tab_browser).classes("w-full p-0 column"):
                render_browser_panel(initial_url="https://www.linkedin.com")

    # --- DIALOG HELPERS ---

    def run_drip_engine():
        result = dispatch_action(
            "communications.deliveries.due.list",
            {"limit": 100},
            actor_type="ui",
            session_id="ui:communications",
        )
        if not result.success:
            ui.notify(result.error or "Due outreach could not be loaded.", type="negative")
            return
        deliveries = result.data.get("deliveries", [])
        blocked = result.data.get("blocked", [])
        with (
            ui.dialog() as dialog,
            ui.card().classes("w-full max-w-3xl max-h-[85vh] p-5 th-card gap-3"),
        ):
            with ui.row().classes("w-full items-center justify-between gap-3"):
                with ui.column().classes("gap-0"):
                    ui.label("Due Outreach Review").classes("th-title")
                    ui.label(
                        "Each email needs its own exact R4 approval. Opening this list sends nothing."
                    ).classes("th-muted")
                ui.button(icon="close", on_click=dialog.close).props("flat round dense")

            review_height = (
                "max-h-[58vh]" if deliveries or blocked else "h-[72px]"
            )
            with ui.scroll_area().classes(f"w-full {review_height}"):
                with ui.column().classes("w-full gap-3 pr-2"):
                    if not deliveries:
                        ui.label("No deliverable outreach steps are due.").classes(
                            "text-sm text-slate-400 py-6"
                        )
                    for item in deliveries:
                        with ui.card().classes(
                            "w-full p-4 bg-[#091520] border border-[#1b3040] rounded-md gap-2"
                        ):
                            with ui.row().classes("w-full items-start justify-between gap-3"):
                                with ui.column().classes("gap-0 min-w-0 grow"):
                                    ui.label(item["candidate_name"]).classes(
                                        "text-sm font-semibold text-slate-100"
                                    )
                                    ui.label(
                                        f"{item['sequence_name']} · Step {item['step_number']}"
                                    ).classes("text-[11px] text-slate-500")
                                if item.get("retry"):
                                    ui.badge("RETRY", color="amber").classes("text-[9px]")
                            ui.label(f"To: {item['recipient']}").classes(
                                "text-xs text-teal-300"
                            )
                            ui.label(f"Subject: {item['subject']}").classes(
                                "text-xs font-medium text-slate-200"
                            )
                            ui.label(item["body"]).classes(
                                "text-xs text-slate-300 whitespace-pre-wrap border-t border-[#1b3040] pt-2"
                            )

                            def request_step_approval(enrollment_id=item["enrollment_id"]):
                                preview = dispatch_preview(
                                    "communications.delivery.send",
                                    {"enrollment_id": enrollment_id},
                                    actor_type="ui",
                                    session_id="ui:communications",
                                )
                                ui.notify(
                                    "Approval request added to Copilot."
                                    if preview.success
                                    else (preview.error or "Approval preview failed."),
                                    type="positive" if preview.success else "negative",
                                )

                            with ui.row().classes("w-full justify-end"):
                                ui.button(
                                    "Request Send Approval",
                                    icon="verified_user",
                                    on_click=request_step_approval,
                                ).classes("th-amber-btn text-xs")
                    for item in blocked:
                        ui.label(
                            f"Enrollment #{item['enrollment_id']} blocked: {item['reason']}"
                        ).classes("text-[11px] text-amber-300")
        dialog.open()

    def open_send_email_dialog():
        with SessionFactory() as db:
            candidates = list_candidates(db)
            options = {
                candidate.id: f"{candidate.full_name} ({candidate.email or 'no email'})"
                for candidate in candidates
            }
        with ui.dialog() as dialog, ui.card().classes("w-full max-w-2xl p-6 th-card gap-3"):
            ui.label("Review a Direct Email").classes("th-title")
            ui.label(
                "This creates an exact approval card in Copilot. Nothing is sent until you approve it."
            ).classes("th-muted")
            candidate_select = (
                ui.select(options, label="Candidate").classes("w-full").props("dark outlined")
            )
            subject_input = (
                ui.input(label="Subject").classes("w-full").props("dark outlined")
            )
            cc_input = ui.input(label="CC (optional)").classes("w-full").props("dark outlined")
            body_input = (
                ui.textarea(label="Message")
                .classes("w-full min-h-[220px]")
                .props("dark outlined autogrow")
            )

            def request_direct_approval():
                if not candidate_select.value or not (subject_input.value or "").strip() or not (
                    body_input.value or ""
                ).strip():
                    ui.notify("Candidate, subject, and message are required.", type="warning")
                    return
                preview = dispatch_preview(
                    "communications.delivery.send",
                    {
                        "candidate_id": candidate_select.value,
                        "subject": subject_input.value.strip(),
                        "body": body_input.value.strip(),
                        "cc": (cc_input.value or "").strip() or None,
                    },
                    actor_type="ui",
                    session_id="ui:communications",
                )
                if not preview.success:
                    ui.notify(preview.error or "Approval preview failed.", type="negative")
                    return
                ui.notify("Approval request added to Copilot.", type="positive")
                dialog.close()

            with ui.row().classes("w-full justify-end gap-2 pt-2"):
                ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
                ui.button(
                    "Request Send Approval",
                    icon="verified_user",
                    on_click=request_direct_approval,
                ).classes("th-amber-btn")
        dialog.open()

    def open_log_communication_dialog():
        with ui.dialog() as dialog, ui.card().classes("w-full max-w-lg p-6 th-card gap-3"):
            ui.label("Log Communication").classes("th-title")
            ui.label("Records communication history only. It does not send a message.").classes(
                "th-muted"
            )

            with SessionFactory() as db:
                cands = list_candidates(db)
                cand_options = {c.id: f"{c.full_name} ({c.email or 'no email'})" for c in cands}

            with ui.column().classes("w-full gap-1"):
                ui.label("Select Candidate").classes("th-caption")
                cand_select = ui.select(cand_options).classes("w-full").props("dark outlined dense")
            with ui.column().classes("w-full gap-1"):
                ui.label("Channel").classes("th-caption")
                channel_select = (
                    ui.select(
                        options=["email", "linkedin", "naukri", "whatsapp", "phone"],
                        value="email",
                    )
                    .classes("w-full")
                    .props("dark outlined dense")
                )
            with ui.column().classes("w-full gap-1"):
                ui.label("Direction").classes("th-caption")
                dir_select = (
                    ui.select(
                        options=["outbound", "inbound"],
                        value="outbound",
                    )
                    .classes("w-full")
                    .props("dark outlined dense")
                )
            with ui.column().classes("w-full gap-1"):
                ui.label("Subject").classes("th-caption")
                subj_in = (
                    ui.input(placeholder="e.g. Follow-up regarding Senior AI Engineer role")
                    .classes("w-full")
                    .props("dark outlined dense")
                )
            with ui.column().classes("w-full gap-1"):
                ui.label("Message Body").classes("th-caption")
                body_in = (
                    ui.textarea(placeholder="Type message content...")
                    .classes("w-full")
                    .props("dark outlined dense")
                )

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button("Cancel", on_click=dialog.close).props("flat").classes("text-[#8195a5]")

                def save_log():
                    if not body_in.value.strip():
                        ui.notify("Message body cannot be empty.", type="negative")
                        return
                    cid = cand_select.value
                    result = dispatch_action(
                        "communications.logs.create",
                        {
                            "candidate_id": cid,
                            "channel": channel_select.value,
                            "direction": dir_select.value,
                            "subject": subj_in.value.strip() or None,
                            "body": body_in.value.strip(),
                        },
                        actor_type="ui",
                        session_id="ui:communications",
                    )
                    if not result.success:
                        ui.notify(
                            result.error or "Communication could not be logged.", type="negative"
                        )
                        return
                    ui.notify("Communication logged. Nothing was sent.", type="positive")
                    dialog.close()
                    refresh_logs()

                ui.button("Save Log", icon="save", on_click=save_log).classes("th-primary-btn")
        dialog.open()

    def open_create_template_dialog():
        with ui.dialog() as dialog, ui.card().classes("w-full max-w-xl p-6 th-card gap-3"):
            ui.label("Create Message Template").classes("th-title")
            ui.label(
                "Use merge tags like {{candidate_name}}, {{job_title}}, {{company}}, {{skills}}."
            ).classes("th-muted")

            with ui.column().classes("w-full gap-1"):
                ui.label("Template Name").classes("th-caption")
                name_in = (
                    ui.input(placeholder="e.g. Initial AI Researcher Email")
                    .classes("w-full")
                    .props("dark outlined dense")
                )
            with ui.column().classes("w-full gap-1"):
                ui.label("Channel").classes("th-caption")
                ch_in = (
                    ui.select(["email", "linkedin", "naukri", "whatsapp"], value="email")
                    .classes("w-full")
                    .props("dark outlined dense")
                )
            with ui.column().classes("w-full gap-1"):
                ui.label("Category").classes("th-caption")
                cat_in = (
                    ui.input(value="Initial Outreach")
                    .classes("w-full")
                    .props("dark outlined dense")
                )
            with ui.column().classes("w-full gap-1"):
                ui.label("Subject").classes("th-caption")
                subj_in = (
                    ui.input(placeholder="Opportunity: {{job_title}} at {{company}}")
                    .classes("w-full")
                    .props("dark outlined dense")
                )
            with ui.column().classes("w-full gap-1"):
                ui.label("Template Body").classes("th-caption")
                body_in = (
                    ui.textarea(placeholder="Hi {{candidate_name}}...")
                    .classes("w-full h-40")
                    .props("dark outlined dense")
                )

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button("Cancel", on_click=dialog.close).props("flat").classes("text-[#8195a5]")

                def save_tmpl():
                    if not name_in.value.strip() or not body_in.value.strip():
                        ui.notify("Name and body are required.", type="negative")
                        return
                    result = dispatch_action(
                        "communications.templates.create",
                        {
                            "name": name_in.value.strip(),
                            "channel": ch_in.value,
                            "category": cat_in.value.strip(),
                            "subject": subj_in.value.strip() or None,
                            "body_template": body_in.value.strip(),
                        },
                        actor_type="ui",
                        session_id="ui:communications",
                    )
                    if not result.success:
                        ui.notify(result.error or "Template could not be saved.", type="negative")
                        return
                    ui.notify("Template saved!", type="positive")
                    dialog.close()
                    refresh_templates()

                ui.button("Save Template", icon="save", on_click=save_tmpl).classes(
                    "th-primary-btn"
                )
        dialog.open()

    def open_template_tester_dialog(tmpl: MessageTemplate):
        with ui.dialog() as dialog, ui.card().classes("w-full max-w-2xl p-6 th-card gap-4"):
            ui.label(f'Personalization Tester: "{tmpl.name}"').classes("th-title")

            with SessionFactory() as db:
                cands = list_candidates(db)
                cand_options = {
                    c.id: f"{c.full_name} ({c.current_title or 'Engineer'})" for c in cands
                }

            with ui.column().classes("w-full gap-1"):
                ui.label("Select Candidate to Preview").classes("th-caption")
                cand_select = ui.select(cand_options).classes("w-full").props("dark outlined dense")
            preview_card = ui.column().classes(
                "w-full p-4 bg-[#091520] border border-[#1b3040] rounded-lg gap-2"
            )

            def update_preview():
                preview_card.clear()
                cid = cand_select.value
                if not cid:
                    with preview_card:
                        ui.label(
                            "Select a candidate above to generate personalized outreach text."
                        ).classes("th-muted")
                    return

                with SessionFactory() as db:
                    cand_obj = db.get(Candidate, cid)
                    rendered = generate_candidate_outreach(
                        template_body=tmpl.body_template,
                        candidate=cand_obj,
                        recruiter_name="Alex (Talent Hunt)",
                    )

                with preview_card:
                    ui.label("Rendered Output:").classes("th-caption")
                    ui.code(rendered).classes("w-full p-3 text-xs text-slate-200 font-mono")

            cand_select.on("update:model-value", update_preview)

            with ui.row().classes("w-full justify-end pt-2"):
                ui.button("Close", on_click=dialog.close).props("flat").classes(
                    "text-[#8195a5] text-xs"
                )
        dialog.open()

    def open_enroll_dialog():
        with ui.dialog() as dialog, ui.card().classes("w-full max-w-md p-6 th-card gap-3"):
            ui.label("Enroll Candidate in Drip Campaign").classes("th-title")

            with SessionFactory() as db:
                cands = list_candidates(db)
                seqs = list_sequences(db)
                cand_opts = {c.id: c.full_name for c in cands}
                seq_opts = {s.id: s.name for s in seqs}

            with ui.column().classes("w-full gap-1"):
                ui.label("Candidate").classes("th-caption")
                cand_sel = ui.select(cand_opts).classes("w-full").props("dark outlined dense")
            with ui.column().classes("w-full gap-1"):
                ui.label("Drip Sequence").classes("th-caption")
                seq_sel = ui.select(seq_opts).classes("w-full").props("dark outlined dense")

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button("Cancel", on_click=dialog.close).props("flat").classes("text-[#8195a5]")

                def do_enroll():
                    if not cand_sel.value or not seq_sel.value:
                        ui.notify("Please select candidate and sequence.", type="warning")
                        return
                    result = dispatch_action(
                        "communications.enrollments.create",
                        {"sequence_id": seq_sel.value, "candidate_id": cand_sel.value},
                        actor_type="ui",
                        session_id="ui:communications",
                    )
                    if not result.success:
                        ui.notify(
                            result.error or "Candidate could not be enrolled.", type="negative"
                        )
                        return
                    ui.notify(
                        "Candidate enrolled in paused state. Nothing was sent.", type="positive"
                    )
                    dialog.close()
                    refresh_sequences()

                ui.button("Enroll", icon="check", on_click=do_enroll).classes("th-primary-btn")
        dialog.open()

    def open_create_sequence_dialog():
        with (
            ui.dialog() as dialog,
            ui.card().classes("w-full max-w-lg p-6 th-card border border-teal-500/30 gap-3"),
        ):
            ui.label("Create Outreach Sequence").classes("text-xl font-bold text-slate-100")
            with ui.column().classes("w-full gap-1"):
                ui.label("Sequence Name").classes("th-caption")
                name_in = (
                    ui.input(placeholder="e.g., Executive Search Drip")
                    .classes("w-full")
                    .props("dark outlined dense")
                )
            with ui.column().classes("w-full gap-1"):
                ui.label("Description").classes("th-caption")
                desc_in = (
                    ui.textarea(placeholder="Optional description…")
                    .classes("w-full")
                    .props("dark outlined dense")
                )

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button("Cancel", on_click=dialog.close).props("flat").classes("text-slate-400")

                def save_seq():
                    if not name_in.value.strip():
                        ui.notify("Name is required.", type="negative")
                        return
                    result = dispatch_action(
                        "communications.sequences.create",
                        {
                            "name": name_in.value.strip(),
                            "description": desc_in.value.strip(),
                            "initial_subject": "Initial Contact",
                            "initial_body": "Hi {{candidate_name}}, would love to connect.",
                        },
                        actor_type="ui",
                        session_id="ui:communications",
                    )
                    if not result.success:
                        ui.notify(result.error or "Sequence could not be created.", type="negative")
                        return
                    ui.notify("Sequence created!", type="positive")
                    dialog.close()
                    refresh_sequences()

                ui.button("Create Sequence", icon="save", on_click=save_seq).classes("th-teal-btn")
        dialog.open()


def communications_page():
    create_layout(render_communications)
