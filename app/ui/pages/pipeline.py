"""NiceGUI Kanban Board for Talent Hunt Candidate Pipeline with Drag-and-Drop."""

from nicegui import ui
from app.ui.layout import create_layout
from app.infrastructure.db import SessionFactory, init_db
from app.hunts.service import list_hunts
from app.hunts.pipeline import (
    get_pipeline_data,
    move_candidate_stage,
    add_candidate_to_hunt,
    remove_candidate,
)


def render_pipeline(hunt_id: int = 1):
    """Render the Kanban pipeline view for a given hunt ID."""
    init_db()

    with SessionFactory() as db:
        hunts_list = list_hunts(db)
        if not hunts_list:
            from app.ui.pages.hunts import seed_demo_hunts_if_empty
            seed_demo_hunts_if_empty(db)
            hunts_list = list_hunts(db)

        current_hunt_id = hunt_id if any(h.id == hunt_id for h in hunts_list) else (hunts_list[0].id if hunts_list else 1)
        pipeline_data = get_pipeline_data(db, current_hunt_id)
        hunt_options = {h.id: h.title for h in hunts_list}

    with ui.column().classes('w-full gap-6'):
        # Header Row
        with ui.row().classes('w-full justify-between items-center'):
            with ui.row().classes('items-center gap-3'):
                ui.button(icon='arrow_back', on_click=lambda: ui.navigate.to('/hunts')).props('flat round dense').classes('text-slate-300')
                with ui.column().classes('gap-0'):
                    hunt_title = pipeline_data.get("hunt_title", "Talent Pipeline")
                    ui.label(hunt_title).classes('text-2xl font-bold text-slate-100')
                    role_sub = f"Target Role: {pipeline_data.get('target_role', 'N/A')} | Total Candidates: {pipeline_data.get('total_candidates', 0)}"
                    ui.label(role_sub).classes('text-xs text-slate-400')

            with ui.row().classes('items-center gap-2'):
                ui.select(
                    options=hunt_options,
                    value=current_hunt_id,
                    on_change=lambda e: ui.navigate.to(f'/hunts/{e.value}/pipeline')
                ).props('dense outlined dark').classes('w-64 text-xs')

                ui.button('Add Candidate', icon='person_add', color='teal', on_click=lambda: open_add_candidate_dialog(current_hunt_id)).classes('th-teal-btn')

        # Kanban Board Area
        board_container = ui.row().classes('w-full overflow-x-auto gap-4 no-wrap pb-6 items-start min-h-[650px]')

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

                        with ui.column().classes('w-72 shrink-0 p-3 th-card rounded-xl border border-teal-900/30 gap-3 min-h-[550px] bg-slate-900/40') as col:
                            # Column Header
                            with ui.row().classes('w-full justify-between items-center px-1 pb-2 border-b border-teal-900/30'):
                                with ui.row().classes('items-center gap-2'):
                                    ui.element('div').classes('w-3 h-3 rounded-full').style(f'background-color: {st_color};')
                                    ui.label(st_name).classes('font-bold text-sm text-slate-200')
                                ui.badge(str(len(candidates)), color='blue-grey').classes('text-xs text-teal-400 font-semibold px-2 py-0.5')

                            def handle_drop(e, target_st_id=st_id):
                                dragged_candidate_id_str = e.args[0]
                                try:
                                    candidate_id = int(dragged_candidate_id_str)
                                    handle_move_candidate(candidate_id, target_st_id)
                                except (ValueError, TypeError):
                                    pass

                            col.on('dragover', js_handler='e => e.preventDefault()')
                            col.on('drop', handle_drop, ['dataTransfer.getData("text/plain")'])

                            with ui.column().classes('w-full gap-3 col grow overflow-y-auto min-h-[450px] p-1'):
                                if not candidates:
                                    with ui.column().classes('w-full h-32 items-center justify-center text-slate-600 text-xs border border-dashed border-slate-800 rounded-lg'):
                                        ui.label('No candidates in stage')

                                for c in candidates:
                                    c_id = c.id
                                    cand_id_val = c.candidate_id
                                    raw_sc = (c.match_score * 100 if c.match_score <= 1.0 else c.match_score) if c.match_score is not None else 88.0
                                    
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
                                        "linkedin_url": c.linkedin_url,
                                        "github_url": c.github_url,
                                    }

                                    with ui.card().classes('w-full p-3 th-card-inner border border-teal-900/20 hover:border-teal-400/50 transition-all cursor-pointer gap-2') as card:
                                        card.props('draggable=true')
                                        card.on('dragstart', js_handler=f'(e) => e.dataTransfer.setData("text/plain", "{c_id}")')

                                        with ui.row().classes('w-full justify-between items-start gap-1').on('click', lambda e, info=cand_info, sc=raw_sc: open_candidate_quick_dialog(info, sc)):
                                            with ui.row().classes('items-center gap-2'):
                                                ui.icon('account_circle', size='sm', color='teal-4')
                                                with ui.column().classes('gap-0'):
                                                    ui.label(cand_info["full_name"]).classes('font-semibold text-sm text-slate-100 hover:text-teal-400 transition-colors line-clamp-1')
                                                    if cand_info["current_title"]:
                                                        ui.label(cand_info["current_title"]).classes('text-[11px] text-slate-400 line-clamp-1')

                                            score_color = 'teal' if raw_sc >= 85 else ('amber' if raw_sc >= 70 else 'indigo')
                                            ui.badge(f"{raw_sc:.0f}% Match", color=score_color).classes('text-[10px] font-bold px-1.5 py-0.5')

                                        if cand_info["current_company"] or cand_info["location"]:
                                            with ui.row().classes('items-center gap-2 text-[11px] text-slate-400 px-1').on('click', lambda e, info=cand_info, sc=raw_sc: open_candidate_quick_dialog(info, sc)):
                                                if cand_info["current_company"]:
                                                    ui.label(f"🏢 {cand_info['current_company']}").classes('line-clamp-1')
                                                if cand_info["location"]:
                                                    ui.label(f"📍 {cand_info['location']}").classes('line-clamp-1')

                                        if cand_info["ai_summary"]:
                                            with ui.card().classes('w-full p-2 bg-slate-900/80 border border-teal-900/20 rounded text-[11px] text-slate-300 cursor-pointer').on('click', lambda e, info=cand_info, sc=raw_sc: open_candidate_quick_dialog(info, sc)):
                                                ui.label(cand_info["ai_summary"]).classes('line-clamp-2')

                                        with ui.row().classes('w-full justify-between items-center pt-1 text-xs'):
                                            with ui.row().classes('items-center gap-1'):
                                                ui.button('View Profile', icon='visibility', on_click=lambda e, info=cand_info, sc=raw_sc: open_candidate_quick_dialog(info, sc)).props('flat dense').classes('text-[10px] text-teal-300 hover:text-teal-200 px-2 py-0.5 bg-teal-950/60 border border-teal-500/30 rounded')
                                                if cand_info["linkedin_url"]:
                                                    ui.button(icon='link', on_click=lambda e, u=cand_info["linkedin_url"]: ui.navigate.to(u, new_tab=True)).props('flat round dense').classes('text-teal-400').tooltip('LinkedIn Profile')

                                            with ui.button(icon='arrow_forward', color='teal').props('flat round dense').tooltip('Move Stage'):
                                                with ui.menu().classes('bg-slate-900 border border-teal-900/40'):
                                                    for target_st in stages:
                                                        if target_st["id"] != st_id:
                                                            ui.menu_item(
                                                                f"Move to {target_st['name']}",
                                                                on_click=lambda e, cid=c_id, tid=target_st["id"]: handle_move_candidate(cid, tid)
                                                            ).classes('text-xs text-slate-200 hover:text-teal-400')
                                                    ui.separator().classes('bg-teal-900/30')
                                                    ui.menu_item(
                                                        'Remove Candidate',
                                                        on_click=lambda e, cid=c_id: handle_remove_candidate(cid)
                                                    ).classes('text-xs text-red-400')

        def handle_move_candidate(candidate_id: int, new_stage_id: int):
            try:
                with SessionFactory() as db:
                    move_candidate_stage(db, candidate_id, new_stage_id)
                ui.notify('Candidate stage updated!', type='positive')
                refresh_board()
            except Exception as e:
                ui.notify(f"Error: {e}", type="negative")

        def handle_remove_candidate(candidate_id: int):
            try:
                with SessionFactory() as db:
                    remove_candidate(db, candidate_id)
                ui.notify('Candidate removed from pipeline.', type='info')
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
                        ui.label(f"📍 Location: {c.get('location') or 'N/A'}").classes('text-slate-300')
                        ui.label(f"📧 Email: {c.get('email') or 'N/A'}").classes('text-slate-300')
                    with ui.column().classes('gap-1'):
                        ui.label(f"📞 Phone: {c.get('phone') or 'N/A'}").classes('text-slate-300')
                        ui.label(f"📋 Status: {c.get('status') or 'Active'}").classes('text-slate-300')

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
                        if c.get("linkedin_url"):
                            ui.button('LinkedIn', icon='link', on_click=lambda e, u=c["linkedin_url"]: ui.navigate.to(u, new_tab=True)).props('flat dense').classes('text-xs text-teal-400')
                        if c.get("github_url"):
                            ui.button('GitHub', icon='code', on_click=lambda e, u=c["github_url"]: ui.navigate.to(u, new_tab=True)).props('flat dense').classes('text-xs text-amber-400')

                    with ui.row().classes('items-center gap-2'):
                        ui.button('Close', on_click=dialog.close).props('flat').classes('text-slate-400 text-xs')
                        target_cid = c.get("candidate_id") or c.get("id")
                        ui.button(
                            'Full 360° Profile Page', icon='open_in_new', color='teal',
                            on_click=lambda e, cid=target_cid: [dialog.close(), ui.navigate.to(f'/candidates/{cid}')]
                        ).classes('th-teal-btn text-xs')

            dialog.open()

        def open_add_candidate_dialog(h_id):
            with ui.dialog() as dialog, ui.card().classes('w-full max-w-lg p-6 th-card border border-teal-500/30'):
                ui.label('Add Candidate to Pipeline').classes('text-xl font-bold text-slate-100 mb-2')

                name_in = ui.input('Full Name', placeholder='e.g., Sarah Jenkins').classes('w-full').props('dark outlined dense')
                title_in = ui.input('Current Title', placeholder='e.g., Senior Backend Engineer').classes('w-full').props('dark outlined dense')
                company_in = ui.input('Current Company', placeholder='e.g., Tech Corp').classes('w-full').props('dark outlined dense')
                email_in = ui.input('Email', placeholder='e.g., sarah@example.com').classes('w-full').props('dark outlined dense')
                score_in = ui.number('AI Match Score (%)', value=88, min=0, max=100).classes('w-full').props('dark outlined dense')
                summary_in = ui.textarea('AI Match Summary / Notes').classes('w-full').props('dark outlined dense')

                with ui.row().classes('w-full justify-end gap-2 mt-4'):
                    ui.button('Cancel', on_click=dialog.close).props('flat').classes('text-slate-400')
                    def save_c():
                        if not name_in.value.strip():
                            ui.notify('Candidate full name is required.', type='negative')
                            return
                        with SessionFactory() as db:
                            add_candidate_to_hunt(
                                db,
                                hunt_id=h_id,
                                full_name=name_in.value.strip(),
                                current_title=title_in.value.strip() or None,
                                current_company=company_in.value.strip() or None,
                                email=email_in.value.strip() or None,
                                match_score=float(score_in.value) if score_in.value else None,
                                ai_summary=summary_in.value.strip() or None,
                            )
                        ui.notify('Candidate added successfully!', type='positive')
                        dialog.close()
                        refresh_board()

                    ui.button('Add Candidate', icon='check', on_click=save_c).classes('th-teal-btn')
            dialog.open()

        refresh_board()


def pipeline_page(hunt_id: int = 1):
    create_layout(lambda: render_pipeline(hunt_id))
