"""NiceGUI Kanban Board for Talent Hunt Candidate Pipeline with Drag-and-Drop."""

from nicegui import ui
from app.actions.api import dispatch_action
from app.ui.layout import create_layout
from app.infrastructure.db import SessionFactory, init_db
from app.hunts.service import list_hunts
from app.hunts.pipeline import (
    get_pipeline_data,
)


def _playbook_author() -> str:
    try:
        return (ui.app.storage.user.get("playbook_author") or "Recruiter").strip() or "Recruiter"
    except Exception:
        return "Recruiter"


def _profile_link_meta(url: str | None) -> tuple[str, str] | None:
    """Return (label, icon) for an external profile URL, or None if empty."""
    u = (url or "").strip()
    if not u:
        return None
    low = u.lower()
    if "linkedin.com" in low:
        return ("LinkedIn", "work")
    if "naukri.com" in low:
        return ("Naukri", "business_center")
    if "github.com" in low:
        return ("GitHub", "code")
    if "indeed.com" in low:
        return ("Indeed", "search")
    return ("Profile", "open_in_new")


def _resolve_external_profile_url(hunt_cand) -> str | None:
    """Prefer hunt-row URL; fall back to master Candidate links."""
    for attr in ("linkedin_url", "portfolio_url", "github_url"):
        val = getattr(hunt_cand, attr, None)
        if val and str(val).strip():
            return str(val).strip()
    master = getattr(hunt_cand, "candidate", None)
    if master is not None:
        for attr in ("linkedin_url", "portfolio_url", "github_url"):
            val = getattr(master, attr, None)
            if val and str(val).strip():
                return str(val).strip()
    return None


def render_pipeline(hunt_id: int = 1):
    """Render the Kanban pipeline view for a given hunt ID."""
    init_db()

    with SessionFactory() as db:
        hunts_list = list_hunts(db)
        if not hunts_list:
            with ui.column().classes('w-full min-h-[60vh] items-center justify-center gap-3'):
                ui.icon('view_kanban', size='xl').classes('text-[#3f6678]')
                ui.label('No pipeline yet').classes('text-lg font-semibold text-[#edf5f7]')
                ui.label('Create a Talent Hunt before adding candidates to a pipeline.').classes(
                    'th-muted text-center'
                )
                ui.button(
                    'Create Talent Hunt',
                    icon='add',
                    on_click=lambda: ui.navigate.to('/hunts'),
                ).classes('th-primary-btn')
            return

        current_hunt_id = hunt_id if any(h.id == hunt_id for h in hunts_list) else hunts_list[0].id
        pipeline_data = get_pipeline_data(db, current_hunt_id)
        hunt_options = {h.id: h.title for h in hunts_list}

    with ui.column().classes('w-full gap-0 th-pipeline-page'):
        # Header Row
        hunt_title = pipeline_data.get("hunt_title", "Talent Pipeline")
        role_sub = f"{pipeline_data.get('target_role', 'N/A')} · {pipeline_data.get('total_candidates', 0)} candidates"
        with ui.row().classes('w-full justify-between items-center gap-5 th-pipeline-header'):
            with ui.row().classes('items-center gap-3'):
                ui.button(icon='arrow_back', on_click=lambda: ui.navigate.to('/hunts')).props('flat round dense').classes('text-[#8195a5]')
                with ui.column().classes('gap-0'):
                    ui.label('Hunts / Pipeline').classes('th-ey')
                    ui.label(hunt_title).classes('th-title')
                    ui.label(role_sub).classes('th-muted')

            with ui.row().classes('items-center gap-2'):
                ui.button(
                    'Playbook', icon='menu_book',
                    on_click=lambda: ui.navigate.to('/playbook')
                ).props('flat dense').classes('text-[#8de8df] text-xs')
                ui.select(
                    options=hunt_options,
                    value=current_hunt_id,
                    on_change=lambda e: ui.navigate.to(f'/hunts/{e.value}/pipeline')
                ).props('dense outlined dark').classes('w-64 text-xs')

                ui.button(
                    icon='add_chart',
                    on_click=lambda: open_add_stage_dialog(current_hunt_id),
                ).props('flat round dense').classes('text-[#8de8df]').tooltip('Add Pipeline stage')

                ui.button('＋ Add Candidate', on_click=lambda: open_add_candidate_dialog(current_hunt_id)).classes('th-primary-btn')

        # Kanban board: horizontal scroll stays under the columns (viewport-bound)
        board_container = ui.element('div').classes('th-pipeline-board')

        def open_triage_dialog(c: dict, action: str):
            """Keep or Pass with optional note → global playbook."""
            title = "Keep for hunt" if action == "keep" else "Pass (log & remove)"
            with ui.dialog() as dialog, ui.card().classes('w-full max-w-md p-5 th-card border border-teal-500/30 gap-3'):
                ui.label(title).classes('text-lg font-bold text-slate-100')
                ui.label(c.get("full_name") or "Candidate").classes('text-sm text-teal-300')
                if c.get("source_platform") or c.get("source_query"):
                    with ui.column().classes('w-full gap-1 p-2 rounded bg-slate-900/70 border border-teal-900/30'):
                        ui.label('Sourcing context').classes('text-[10px] font-bold text-teal-400 uppercase')
                        if c.get("source_platform"):
                            ui.label(f"Platform: {c['source_platform']}").classes('text-xs text-slate-300')
                        if c.get("source_query"):
                            ui.label(f"Query: {c['source_query']}").classes('text-xs text-slate-400')
                note_in = ui.textarea(
                    placeholder='Optional note — what worked / why pass…'
                ).classes('w-full').props('dark outlined dense')
                with ui.row().classes('w-full justify-end gap-2 mt-2'):
                    ui.button('Cancel', on_click=dialog.close).props('flat').classes('text-slate-400 text-xs')

                    def confirm():
                        note = (note_in.value or "").strip() or None
                        author = _playbook_author()
                        try:
                            action_result = dispatch_action(
                                "pipeline.triage",
                                {
                                    "hunt_candidate_id": c["id"], "decision": action,
                                    "note": note, "author": author,
                                },
                                actor_type="ui",
                                session_id=f"hunt_{current_hunt_id}",
                            )
                            if not action_result.success:
                                ui.notify(action_result.error or "Triage failed", type="negative")
                                return
                            result = action_result.data or {}
                            msg = (
                                f"Kept — logged to Playbook"
                                + (f" → {result.get('moved_to_stage')}" if result.get("moved_to_stage") else "")
                                if action == "keep"
                                else "Passed — removed & logged to Playbook"
                            )
                            ui.notify(msg, type="positive" if action == "keep" else "info")
                            dialog.close()
                            refresh_board()
                        except Exception as exc:
                            ui.notify(f"Error: {exc}", type="negative")

                    btn_label = "Keep & log" if action == "keep" else "Pass & log"
                    btn_color = "teal" if action == "keep" else "orange"
                    ui.button(btn_label, icon='check' if action == "keep" else 'thumb_down', on_click=confirm).props(
                        f'color={btn_color}'
                    ).classes('text-xs')
            dialog.open()

        def refresh_board():
            board_container.clear()
            with board_container:
                with SessionFactory() as db:
                    p_data = get_pipeline_data(db, current_hunt_id)

                    stages = p_data.get("stages", [])

                    for stage in stages:
                        st_id = stage["id"]
                        st_name = stage["name"]
                        st_color = stage["color"]
                        candidates = stage["candidates"]
                        is_sourced = (st_name or "").strip().lower() == "sourced"

                        with ui.column().classes('th-kanban-col gap-2') as col:
                            # Column Header
                            with ui.row().classes('w-full justify-between items-center px-1 pb-2 shrink-0'):
                                with ui.row().classes('items-center gap-2'):
                                    ui.element('div').classes('w-2 h-2 rounded-full').style(f'background-color: {st_color};')
                                    ui.label(st_name.upper()).classes('th-muted font-semibold tracking-wide')
                                ui.element('span').classes('th-pill').text = str(len(candidates))

                            def handle_drop(e, target_st_id=st_id):
                                dragged_candidate_id_str = e.args[0]
                                try:
                                    candidate_id = int(dragged_candidate_id_str)
                                    handle_move_candidate(candidate_id, target_st_id)
                                except (ValueError, TypeError):
                                    pass

                            col.on('dragover', js_handler='e => e.preventDefault()')
                            col.on('drop', handle_drop, ['dataTransfer.getData("text/plain")'])

                            with ui.column().classes('w-full gap-3 th-kanban-cards p-1'):
                                if not candidates:
                                    with ui.column().classes('w-full h-32 items-center justify-center text-slate-600 text-xs border border-dashed border-slate-800 rounded-lg'):
                                        ui.label('No candidates in stage')

                                for c in candidates:
                                    c_id = c.id
                                    raw_sc = (c.match_score * 100 if c.match_score <= 1.0 else c.match_score) if c.match_score is not None else 88.0

                                    profile_url = _resolve_external_profile_url(c)
                                    profile_meta = _profile_link_meta(profile_url)

                                    cand_info = {
                                        "id": c.id,
                                        "candidate_id": c.candidate_id,
                                        "full_name": c.full_name or "Candidate",
                                        "current_title": c.current_title,
                                        "current_company": c.current_company,
                                        "location": c.location,
                                        "email": c.email,
                                        "phone": c.phone,
                                        "status": c.status or "Active",
                                        "ai_summary": c.ai_summary,
                                        "notes": c.notes,
                                        "linkedin_url": profile_url or c.linkedin_url,
                                        "github_url": c.github_url,
                                        "profile_url": profile_url,
                                        "profile_label": profile_meta[0] if profile_meta else None,
                                        "profile_icon": profile_meta[1] if profile_meta else None,
                                        "source_platform": getattr(c, "source_platform", None),
                                        "source_query": getattr(c, "source_query", None),
                                        "stage_name": st_name,
                                    }

                                    with ui.card().classes('w-full th-candidate-card hover:border-[#19d3c5]/50 transition-all cursor-pointer gap-2') as card:
                                        card.props('draggable=true')
                                        card.on('dragstart', js_handler=f'(e) => e.dataTransfer.setData("text/plain", "{c_id}")')

                                        with ui.row().classes('w-full justify-between items-start gap-1').on('click', lambda e, info=cand_info, sc=raw_sc: open_candidate_quick_dialog(info, sc)):
                                            with ui.row().classes('items-center gap-2'):
                                                initial = (cand_info["full_name"] or "?")[0].upper()
                                                ui.element('span').classes('th-avatar').text = initial
                                                with ui.column().classes('gap-0'):
                                                    ui.label(cand_info["full_name"]).classes('font-semibold text-[10px] text-[#edf5f7] line-clamp-1')
                                                    if cand_info["current_title"]:
                                                        ui.label(cand_info["current_title"]).classes('text-[10px] text-[#8195a5] line-clamp-1')

                                            ui.element('span').classes('th-pill').text = f"{raw_sc:.0f}% match"

                                        if cand_info["current_company"] or cand_info["location"]:
                                            with ui.row().classes('items-center gap-2 text-[10px] text-[#8195a5] px-1').on('click', lambda e, info=cand_info, sc=raw_sc: open_candidate_quick_dialog(info, sc)):
                                                if cand_info["current_company"]:
                                                    ui.label(cand_info['current_company']).classes('line-clamp-1')
                                                if cand_info["location"]:
                                                    ui.label(cand_info['location']).classes('line-clamp-1')

                                        if cand_info.get("source_platform"):
                                            ui.label(f"via {cand_info['source_platform']}").classes('text-[9px] text-[#19d3c5]/80 px-1')

                                        if cand_info["ai_summary"]:
                                            with ui.card().classes('w-full p-2 bg-[#091520] border border-[#1b3040] rounded text-[10px] text-[#8195a5] cursor-pointer').on('click', lambda e, info=cand_info, sc=raw_sc: open_candidate_quick_dialog(info, sc)):
                                                ui.label(cand_info["ai_summary"]).classes('line-clamp-2')

                                        if is_sourced:
                                            with ui.row().classes('w-full gap-1 pt-1'):
                                                ui.button(
                                                    'Keep', icon='thumb_up',
                                                    on_click=lambda e, info=cand_info: open_triage_dialog(info, "keep")
                                                ).props('dense flat no-caps').classes('text-[10px] text-teal-300 flex-1')
                                                ui.button(
                                                    'Pass', icon='thumb_down',
                                                    on_click=lambda e, info=cand_info: open_triage_dialog(info, "pass")
                                                ).props('dense flat no-caps').classes('text-[10px] text-orange-300 flex-1')

                                        with ui.row().classes('w-full justify-between items-center pt-1 text-xs gap-1'):
                                            with ui.row().classes('items-center gap-1 flex-wrap'):
                                                ui.button(
                                                    'View', icon='visibility',
                                                    on_click=lambda e, info=cand_info, sc=raw_sc: open_candidate_quick_dialog(info, sc),
                                                ).props('flat dense no-caps').classes('text-[10px] text-[#8de8df] px-2 py-0.5')
                                                if cand_info.get("profile_url") and cand_info.get("profile_label"):
                                                    ui.button(
                                                        cand_info["profile_label"],
                                                        icon=cand_info.get("profile_icon") or "open_in_new",
                                                        on_click=lambda e, u=cand_info["profile_url"]: ui.navigate.to(u, new_tab=True),
                                                    ).props('flat dense no-caps').classes(
                                                        'text-[10px] text-[#19d3c5] px-2 py-0.5 border border-[#19d3c5]/40 rounded'
                                                    ).tooltip(f'Open {cand_info["profile_label"]} profile')

                                            with ui.button(icon='arrow_forward').props('flat round dense').classes('text-[#19d3c5]').tooltip('Move Stage'):
                                                with ui.menu().classes('bg-[#0e1b28] border border-[#1b3040]'):
                                                    for target_st in stages:
                                                        if target_st["id"] != st_id:
                                                            ui.menu_item(
                                                                f"Move to {target_st['name']}",
                                                                on_click=lambda e, cid=c_id, tid=target_st["id"]: handle_move_candidate(cid, tid)
                                                            ).classes('text-xs text-[#edf5f7] hover:text-[#19d3c5]')
                                                    ui.separator().classes('bg-[#1b3040]')
                                                    ui.menu_item(
                                                        'Remove Candidate',
                                                        on_click=lambda e, cid=c_id: handle_remove_candidate(cid)
                                                    ).classes('text-xs text-red-400')

        def handle_move_candidate(candidate_id: int, new_stage_id: int):
            try:
                result = dispatch_action(
                    "pipeline.move",
                    {"hunt_candidate_id": candidate_id, "stage_id": new_stage_id},
                    actor_type="ui",
                    session_id=f"hunt_{hunt_id}",
                )
                if not result.success:
                    raise RuntimeError(result.error or "Candidate move failed.")
                ui.notify('Candidate stage updated. Undo is available in Action History.', type='positive')
                refresh_board()
            except Exception as e:
                ui.notify(f"Error: {e}", type="negative")

        def handle_remove_candidate(candidate_id: int):
            try:
                result = dispatch_action(
                    "pipeline.remove",
                    {"hunt_candidate_id": candidate_id},
                    actor_type="ui",
                    session_id=f"hunt_{current_hunt_id}",
                )
                if not result.success:
                    raise RuntimeError(result.error or "Candidate removal failed.")
                ui.notify('Removed from this Pipeline. Master profile preserved; Undo is available.', type='info')
                refresh_board()
            except Exception as e:
                ui.notify(f"Error: {e}", type="negative")

        def open_candidate_quick_dialog(c: dict, score: float):
            with ui.dialog() as dialog, ui.card().classes('w-full max-w-2xl p-6 th-card border border-teal-500/40 gap-4'):
                with ui.row().classes('w-full justify-between items-start'):
                    with ui.row().classes('items-center gap-3'):
                        ui.avatar(c["full_name"][0].upper() if c.get("full_name") else '?', color='teal-9', text_color='teal-2').classes('font-bold text-lg')
                        with ui.column().classes('gap-0'):
                            ui.label(c["full_name"]).classes('text-xl font-bold text-slate-100')
                            ui.label(f"{c.get('current_title') or 'Candidate'} • {c.get('current_company') or 'N/A'}").classes('text-xs text-slate-400 font-medium')

                    sc_color = 'teal' if score >= 85 else ('amber' if score >= 70 else 'indigo')
                    ui.badge(f"{score:.0f}% Fit Match", color=sc_color).classes('text-xs font-bold px-2 py-1')

                ui.separator().classes('bg-teal-900/30 my-1')

                with ui.row().classes('w-full justify-between items-center text-xs text-slate-300 gap-4 bg-slate-900/60 p-3 rounded-lg border border-teal-900/20'):
                    with ui.column().classes('gap-1'):
                        ui.label(f"Location: {c.get('location') or 'N/A'}").classes('text-slate-300')
                        ui.label(f"Email: {c.get('email') or 'N/A'}").classes('text-slate-300')
                    with ui.column().classes('gap-1'):
                        ui.label(f"Phone: {c.get('phone') or 'N/A'}").classes('text-slate-300')
                        ui.label(f"Status: {c.get('status') or 'Active'}").classes('text-slate-300')

                if c.get("source_platform") or c.get("source_query"):
                    with ui.column().classes('w-full gap-1'):
                        ui.label('Sourcing context').classes('text-xs font-bold text-teal-400')
                        bits = []
                        if c.get("source_platform"):
                            bits.append(f"Platform: {c['source_platform']}")
                        if c.get("source_query"):
                            bits.append(f"Query: {c['source_query']}")
                        ui.label(" · ".join(bits)).classes('text-xs text-slate-400')

                if c.get("ai_summary"):
                    with ui.column().classes('w-full gap-1'):
                        ui.label('AI Sourcing Match Summary').classes('text-xs font-bold text-teal-400')
                        with ui.card().classes('w-full p-3 bg-slate-900/80 border border-teal-900/30 rounded-lg text-xs text-slate-300 leading-relaxed'):
                            ui.markdown(c["ai_summary"])

                if c.get("notes"):
                    with ui.column().classes('w-full gap-1'):
                        ui.label('Recruiter Notes').classes('text-xs font-bold text-slate-300')
                        ui.label(c["notes"]).classes('text-xs text-slate-400 bg-slate-900/50 p-2 rounded border border-slate-800')

                with ui.row().classes('w-full justify-between items-center mt-3 pt-2 border-t border-teal-900/30'):
                    with ui.row().classes('items-center gap-2'):
                        if c.get("profile_url") and c.get("profile_label"):
                            ui.button(
                                c["profile_label"],
                                icon=c.get("profile_icon") or "open_in_new",
                                on_click=lambda e, u=c["profile_url"]: ui.navigate.to(u, new_tab=True),
                            ).props('flat dense').classes('text-xs text-teal-300')
                        elif c.get("linkedin_url"):
                            ui.button(
                                'LinkedIn', icon='work',
                                on_click=lambda e, u=c["linkedin_url"]: ui.navigate.to(u, new_tab=True),
                            ).props('flat dense').classes('text-xs text-teal-400')
                        if c.get("github_url"):
                            ui.button('GitHub', icon='code', on_click=lambda e, u=c["github_url"]: ui.navigate.to(u, new_tab=True)).props('flat dense').classes('text-xs text-amber-400')

                    with ui.row().classes('items-center gap-2'):
                        if (c.get("stage_name") or "").lower() == "sourced":
                            ui.button('Keep', icon='thumb_up', on_click=lambda: [dialog.close(), open_triage_dialog(c, "keep")]).props('flat dense').classes('text-xs text-teal-300')
                            ui.button('Pass', icon='thumb_down', on_click=lambda: [dialog.close(), open_triage_dialog(c, "pass")]).props('flat dense').classes('text-xs text-orange-300')
                        ui.button('Close', on_click=dialog.close).props('flat').classes('text-slate-400 text-xs')
                        target_cid = c.get("candidate_id") or c.get("id")
                        ui.button(
                            'Full 360° Profile Page', icon='open_in_new', color='teal',
                            on_click=lambda e, cid=target_cid: [dialog.close(), ui.navigate.to(f'/candidates/{cid}')]
                        ).classes('th-teal-btn text-xs')

            dialog.open()

        def open_add_candidate_dialog(h_id):
            with ui.dialog() as dialog, ui.card().classes('w-full max-w-lg p-6 th-card gap-3'):
                ui.label('Add Candidate to Pipeline').classes('th-title')

                with ui.column().classes('w-full gap-1'):
                    ui.label('Full Name').classes('th-caption')
                    name_in = ui.input(placeholder='e.g., Sarah Jenkins').classes('w-full').props('dark outlined dense')
                with ui.column().classes('w-full gap-1'):
                    ui.label('Current Title').classes('th-caption')
                    title_in = ui.input(placeholder='e.g., Senior Backend Engineer').classes('w-full').props('dark outlined dense')
                with ui.column().classes('w-full gap-1'):
                    ui.label('Current Company').classes('th-caption')
                    company_in = ui.input(placeholder='e.g., Tech Corp').classes('w-full').props('dark outlined dense')
                with ui.column().classes('w-full gap-1'):
                    ui.label('Email').classes('th-caption')
                    email_in = ui.input(placeholder='e.g., sarah@example.com').classes('w-full').props('dark outlined dense')
                with ui.column().classes('w-full gap-1'):
                    ui.label('AI Match Summary / Notes').classes('th-caption')
                    summary_in = ui.textarea(placeholder='Notes…').classes('w-full').props('dark outlined dense')

                with ui.row().classes('w-full justify-end gap-2 mt-4'):
                    ui.button('Cancel', on_click=dialog.close).props('flat').classes('text-[#8195a5]')
                    def save_c():
                        if not name_in.value.strip():
                            ui.notify('Candidate full name is required.', type='negative')
                            return
                        result = dispatch_action(
                            "candidates.create",
                            {
                                "hunt_id": h_id,
                                "full_name": name_in.value.strip(),
                                "current_title": title_in.value.strip() or None,
                                "current_company": company_in.value.strip() or None,
                                "email": email_in.value.strip() or None,
                                "summary": summary_in.value.strip() or None,
                                "status": "Sourced",
                            },
                            actor_type="ui",
                            session_id=f"hunt_{h_id}",
                        )
                        if not result.success:
                            ui.notify(result.error or 'Candidate could not be added.', type='negative')
                            return
                        if (result.data or {}).get("status") == "conflict":
                            ui.notify(
                                f"Possible duplicate: {(result.data or {}).get('candidate_name')}. Review the existing profile.",
                                type='warning',
                            )
                            return
                        ui.notify('Candidate added to the Common Pool and this Pipeline. Undo is available.', type='positive')
                        dialog.close()
                        refresh_board()

                    ui.button('Add Candidate', icon='check', on_click=save_c).classes('th-primary-btn')
            dialog.open()

        def open_add_stage_dialog(h_id):
            with ui.dialog() as dialog, ui.card().classes('w-full max-w-sm p-5 th-card gap-3'):
                ui.label('Add Pipeline Stage').classes('text-lg font-bold text-[#edf5f7]')
                name_in = ui.input(placeholder='e.g., Technical Review').props(
                    'dark outlined dense autofocus'
                ).classes('w-full')
                color_in = ui.color_input(label='Stage color', value='#19d3c5').classes('w-full')
                with ui.row().classes('w-full justify-end gap-2'):
                    ui.button('Cancel', on_click=dialog.close).props('flat')

                    def save_stage():
                        name = (name_in.value or '').strip()
                        if not name:
                            ui.notify('Stage name is required.', type='negative')
                            return
                        result = dispatch_action(
                            'pipeline.stages.add',
                            {'hunt_id': h_id, 'name': name, 'color': color_in.value or '#19d3c5'},
                            actor_type='ui',
                            session_id=f'hunt_{h_id}',
                        )
                        if not result.success:
                            ui.notify(result.error or 'Stage could not be added.', type='negative')
                            return
                        ui.notify('Pipeline stage added. Undo is available.', type='positive')
                        dialog.close()
                        refresh_board()

                    ui.button('Add Stage', icon='add', on_click=save_stage).classes('th-primary-btn')
            dialog.open()

        refresh_board()


def pipeline_page(hunt_id: int = 1):
    create_layout(lambda: render_pipeline(hunt_id))
