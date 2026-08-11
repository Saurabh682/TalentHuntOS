"""NiceGUI Talent Hunts Campaign Management Page."""

from nicegui import ui
from app.actions.api import approve_and_dispatch, cancel_approval, dispatch_action, dispatch_preview
from app.ui.layout import create_layout
from app.infrastructure.db import SessionFactory, init_db
from app.hunts.service import list_hunts, get_hunt, get_hunt_metrics


def seed_demo_hunts_if_empty(db):
    """No-op: Demo hunts disabled as requested."""
    pass


def _hunt_form_fields(
    *,
    title: str = "",
    role: str = "",
    location: str = "India",
    experience: str = "",
    salary: str = "",
    skills: str = "",
    industry: str = "",
    description: str = "",
):
    """Shared Create/Edit hunt fields — keep both dialogs identical."""
    with ui.column().classes('w-full gap-1'):
        ui.label('Hunt Title').classes('th-caption')
        title_in = ui.input(
            value=title,
            placeholder='e.g., Spine Animator Hunt',
        ).classes('w-full').props('dark outlined dense')

    with ui.row().classes('w-full gap-3'):
        with ui.column().classes('grow gap-1'):
            ui.label('Role').classes('th-caption')
            role_in = ui.input(
                value=role,
                placeholder='e.g., Spine Animator',
            ).classes('w-full').props('dark outlined dense')
        with ui.column().classes('grow gap-1'):
            ui.label('Location').classes('th-caption')
            loc_in = ui.input(
                value=location,
                placeholder='e.g., India',
            ).classes('w-full').props('dark outlined dense')

    with ui.row().classes('w-full gap-3'):
        with ui.column().classes('grow gap-1'):
            ui.label('Experience').classes('th-caption')
            exp_in = ui.input(
                value=experience,
                placeholder='e.g., 4–8 years',
            ).classes('w-full').props('dark outlined dense')
        with ui.column().classes('grow gap-1'):
            ui.label('Salary Range (optional)').classes('th-caption')
            salary_in = ui.input(
                value=salary,
                placeholder='e.g., ₹15–25 LPA — leave blank if unknown',
            ).classes('w-full').props('dark outlined dense')

    with ui.row().classes('w-full gap-3'):
        with ui.column().classes('grow gap-1'):
            ui.label('Required Skills').classes('th-caption')
            skills_in = ui.input(
                value=skills,
                placeholder='e.g., Spine, 2D Animation, After Effects',
            ).classes('w-full').props('dark outlined dense')
        with ui.column().classes('grow gap-1'):
            ui.label('Industry (optional)').classes('th-caption')
            industry_in = ui.input(
                value=industry,
                placeholder='e.g., SaaS, FinTech, Animation',
            ).classes('w-full').props('dark outlined dense')

    with ui.column().classes('w-full gap-1'):
        ui.label('Role Summary').classes('th-caption')
        desc_in = ui.textarea(
            value=description,
            placeholder='Provide job responsibilities...',
        ).classes('w-full').props('dark outlined dense')

    return title_in, role_in, loc_in, exp_in, salary_in, skills_in, industry_in, desc_in


def render_hunts():
    """Render the Hunts Campaign page content."""
    init_db()
    with SessionFactory() as db:
        seed_demo_hunts_if_empty(db)

    selected_status = {"value": "All"}
    render_grid_ref = {"fn": lambda: None}

    def open_create_hunt_dialog():
        with ui.dialog() as dialog, ui.card().classes('w-full max-w-2xl p-6 th-card gap-4'):
            ui.label('Hunts / Create').classes('th-ey')
            ui.label('Create New Talent Hunt').classes('th-title')
            ui.label('Set up a new AI-powered sourcing campaign in a few steps.').classes('th-muted')

            title_in, role_in, loc_in, exp_in, salary_in, skills_in, industry_in, desc_in = _hunt_form_fields()

            with ui.row().classes('w-full justify-end gap-3 mt-4'):
                ui.button('Cancel', on_click=dialog.close).props('flat').classes('text-[#8195a5]')
                def save():
                    if not title_in.value.strip():
                        ui.notify('Please provide a campaign title', type='negative')
                        return

                    try:
                        from app.hunts.launch import launch_hunt_and_start_sourcing
                        result = launch_hunt_and_start_sourcing(
                            title=title_in.value.strip(),
                            target_role=role_in.value.strip() or None,
                            location=loc_in.value.strip() or None,  # defaults to India
                            salary_range=salary_in.value.strip() or None,
                            description=desc_in.value.strip() or None,
                            required_skills=skills_in.value.strip() or None,
                            experience=exp_in.value.strip() or None,
                            industry=industry_in.value.strip() or None,
                        )
                        ui.notify(
                            f'Hunt launched — Copilot is sourcing LinkedIn + Naukri for {result["location"]}',
                            type='positive',
                        )
                        dialog.close()
                        # Open pipeline so Copilot remounts on this hunt session and auto-runs sourcing
                        ui.navigate.to(f'/hunts/{result["hunt_id"]}/pipeline')
                    except Exception as e:
                        ui.notify(f'Launch failed: {e}', type='negative')

                ui.button('Launch Hunt →', icon='rocket_launch', on_click=save).classes('th-primary-btn')
        dialog.open()

    with ui.column().classes('w-full gap-0'):
        # Header Row
        with ui.row().classes('w-full justify-between items-center gap-5 mb-[22px]'):
            with ui.column().classes('gap-0'):
                ui.label('Recruitment campaigns').classes('th-ey')
                ui.label('Talent Hunts').classes('th-title')
                ui.label('Create, monitor and execute AI-driven sourcing campaigns.').classes('th-muted')
            ui.button('＋ New', on_click=open_create_hunt_dialog).classes('th-primary-btn')

        # Filter & Search Bar
        with ui.row().classes('w-full items-center gap-2 mb-[13px] flex-wrap'):
            for status_opt in ["All", "Active", "Draft", "Paused", "Completed"]:
                ui.button(
                    status_opt,
                    on_click=lambda e, s=status_opt: set_filter(s)
                ).props('dense flat no-caps').classes(
                    'th-tab th-tab-on' if status_opt == 'All' else 'th-tab'
                )
            search_input = ui.input(placeholder='Search…').classes('grow text-sm').props('dense rounded outlined dark')

        grid_container = ui.row().classes('w-full gap-[13px] items-stretch')

        def render_grid():
            grid_container.clear()
            with SessionFactory() as db:
                all_hunts = list_hunts(db)

                filtered = [
                    h for h in all_hunts
                    if (selected_status["value"] == "All" or h.status == selected_status["value"])
                    and (not search_input.value or search_input.value.lower() in h.title.lower() or (h.target_role and search_input.value.lower() in h.target_role.lower()))
                ]

                with grid_container:
                    if not filtered:
                        with ui.card().classes('w-full p-12 th-card items-center justify-center text-center gap-4'):
                            ui.icon('search_off', size='48px', color='slate-500')
                            ui.label('No Talent Hunt Campaigns Found').classes('th-subheading text-slate-100')
                            ui.label('Launch your first AI-driven talent hunt campaign to start sourcing top candidates.').classes('th-body text-slate-400 max-w-md')
                            ui.button(
                                'Launch First Talent Hunt', icon='rocket_launch',
                                on_click=open_create_hunt_dialog
                            ).classes('th-teal-btn mt-2')
                        return

                    for hunt in filtered:
                        metrics = get_hunt_metrics(db, hunt.id)

                        with ui.card().classes('col-12 col-md-6 col-lg-4 p-5 th-card flex flex-col justify-between hover:border-[#19d3c5]/50 transition-all duration-200'):
                            with ui.column().classes('w-full gap-2'):
                                with ui.row().classes('w-full justify-between items-start gap-2'):
                                    ui.label(hunt.title).classes('text-[13px] font-semibold text-[#edf5f7] line-clamp-1')
                                    status_bg = 'th-pill th-pill-green' if hunt.status == 'Active' else 'th-pill'
                                    ui.element('span').classes(status_bg).text = hunt.status

                                exp_req = None
                                required_skills_list = []
                                if hunt.search_config:
                                    sc = hunt.search_config
                                    if hasattr(sc, 'keywords') and sc.keywords and 'Exp:' in sc.keywords:
                                        exp_req = sc.keywords.split('|')[0].replace('Exp:', '').strip()
                                    elif getattr(sc, 'experience_years_min', None):
                                        exp_req = f"{sc.experience_years_min}+ yrs exp"

                                    if hasattr(sc, 'required_skills') and sc.required_skills:
                                        required_skills_list = [s.strip() for s in sc.required_skills.split(',') if s.strip()]

                                if hunt.target_role or hunt.location or exp_req:
                                    with ui.row().classes('items-center gap-3 text-[11px] text-[#8195a5] flex-wrap'):
                                        if hunt.target_role:
                                            with ui.row().classes('items-center gap-1'):
                                                ui.icon('work_outline', size='xs').classes('text-[#19d3c5]')
                                                ui.label(hunt.target_role)
                                        if hunt.location:
                                            with ui.row().classes('items-center gap-1'):
                                                ui.icon('place', size='xs').classes('text-[#8195a5]')
                                                ui.label(hunt.location)
                                        if exp_req:
                                            with ui.row().classes('items-center gap-1'):
                                                ui.icon('history_edu', size='xs').classes('text-[#8195a5]')
                                                ui.label(exp_req)

                                if required_skills_list:
                                    with ui.row().classes('items-center gap-1 mt-1 flex-wrap'):
                                        for sk in required_skills_list[:4]:
                                            ui.element('span').classes('th-pill').text = sk

                                if hunt.description:
                                    ui.label(hunt.description).classes('text-[11px] text-[#8195a5] mt-1 line-clamp-2')

                            ui.separator().classes('bg-[#1b3040] my-3')

                            with ui.row().classes('w-full justify-around items-center bg-[#091520] p-2.5 rounded-lg border border-[#1b3040] mb-4'):
                                with ui.column().classes('items-center gap-0 cursor-pointer hover:opacity-80 transition-opacity').on(
                                    'click', lambda e, hid=hunt.id: ui.navigate.to(f'/hunts/{hid}/pipeline')
                                ):
                                    ui.label(str(metrics.get("total_candidates", 0))).classes('text-lg font-bold text-[#19d3c5]')
                                    ui.label('In pipeline').classes('text-[10px] text-[#8195a5]')
                                
                                ui.separator().props('vertical').classes('h-8 bg-[#1b3040]')

                                with ui.column().classes('items-center gap-0'):
                                    raw_sc = metrics.get('avg_match_score', 0)
                                    formatted_sc = f"{raw_sc:.1f}%" if isinstance(raw_sc, (int, float)) else f"{raw_sc}%"
                                    ui.label(formatted_sc).classes('text-lg font-bold text-[#edf5f7]')
                                    ui.label('Avg Match').classes('text-[10px] text-[#8195a5]')

                                ui.separator().props('vertical').classes('h-8 bg-[#1b3040]')

                                with ui.column().classes('items-center gap-0'):
                                    ui.label(str(metrics.get("hired_count", 0))).classes('text-lg font-bold text-[#19d3c5]')
                                    ui.label('Hired').classes('text-[10px] text-[#8195a5]')

                            with ui.column().classes('w-full gap-2 mt-auto pt-2'):
                                ui.button(
                                    'Open', icon='view_kanban',
                                    on_click=lambda e, hid=hunt.id: ui.navigate.to(f'/hunts/{hid}/pipeline')
                                ).classes('w-full th-primary-btn text-xs')

                                with ui.row().classes('w-full justify-between items-center px-1 pt-1'):
                                    ui.button(
                                        icon='edit',
                                        on_click=lambda e, hid=hunt.id: open_edit_hunt_dialog(hid)
                                    ).props('flat round dense').classes('text-[#8195a5] hover:text-[#19d3c5]').tooltip('Edit Campaign')

                                    ui.button(
                                        icon='auto_awesome',
                                        on_click=lambda e, hid=hunt.id, t=hunt.title: trigger_ai_sourcing(hid, t)
                                    ).props('flat round dense').classes('text-[#8195a5] hover:text-[#19d3c5]').tooltip('Source until 25 in pipeline')

                                    toggle_icon = 'pause' if hunt.status == 'Active' else 'play_arrow'
                                    ui.button(
                                        icon=toggle_icon,
                                        on_click=lambda e, hid=hunt.id, st=hunt.status: toggle_hunt_status(hid, st)
                                    ).props('flat round dense').classes('text-[#8195a5] hover:text-[#edf5f7]').tooltip('Pause / Resume Campaign')

                                    ui.button(
                                        icon='delete_outline',
                                        on_click=lambda e, hid=hunt.id, t=hunt.title: confirm_delete_hunt(hid, t)
                                    ).props('flat round dense').classes('text-[#8195a5] hover:text-red-400').tooltip('Archive Talent Hunt')

        render_grid_ref["fn"] = render_grid

        def set_filter(status_name):
            selected_status["value"] = status_name
            render_grid()

        def trigger_ai_sourcing(hunt_id: int, title: str):
            """Find up to 25 lightweight profiles and send them to recruiter review."""
            import threading
            try:
                from app.infrastructure.db import SessionFactory
                from app.hunts.service import get_hunt
                from app.candidates.discovery import discovery_counts
                from app.hunts.web_sourcing import source_candidates_for_hunt
                from app.hunts import sourcing_jobs

                with SessionFactory() as db:
                    hunt = get_hunt(db, hunt_id)
                    if not hunt:
                        ui.notify("Hunt not found", type="negative")
                        return
                    have = discovery_counts(db, hunt_id=hunt_id).get("reviewable", 0)
                    fill_to = 25
                    need = max(0, fill_to - have)
                    role = (hunt.target_role or hunt.title or "Professional").strip()
                    loc = (hunt.location or "India").strip() or "India"
                    skills = ""
                    if hunt.search_config and hunt.search_config.required_skills:
                        skills = hunt.search_config.required_skills

                if need == 0:
                    ui.notify(f"'{title}' already has {have} profiles awaiting review.", type="info")
                    render_grid()
                    return

                job_id = sourcing_jobs.start_job(
                    hunt_id=hunt_id,
                    hunt_title=title,
                    label=f"Find {fill_to} · {role}",
                    payload={
                        "role": role,
                        "skills": skills,
                        "location": loc,
                        "target_count": fill_to,
                        "platforms": [],
                        "approval_required": True,
                        "time_budget_sec": 180,
                    },
                )
                ui.notify(
                    f"Searching for '{title}' - review queue {have}/{fill_to}. "
                    "You can keep chatting while it runs.",
                    type="info",
                )

                def _bg():
                    try:
                        source_candidates_for_hunt(
                            hunt_id,
                            role=role,
                            skills=skills,
                            location=loc,
                            hunt_title=title,
                            max_per_query=10,
                            enrich_pages=True,
                            verify_with_ai=False,
                            job_id=job_id,
                            target_added=fill_to,
                            approval_required=True,
                            time_budget_sec=180,
                        )
                    except Exception as exc:
                        sourcing_jobs.finish_job(
                            job_id, status="error", message=str(exc), error=str(exc)
                        )

                threading.Thread(target=_bg, daemon=True, name=f"hunt-source-{hunt_id}").start()
                # Refresh soon so banner/job state is visible; user can refresh again later
                ui.timer(2.0, render_grid, once=True)
            except Exception as e:
                ui.notify(f"Sourcing error: {e}", type="negative")

        def toggle_hunt_status(hunt_id, current_status):
            try:
                new_st = 'Paused' if current_status == 'Active' else 'Active'
                result = dispatch_action(
                    'hunts.status.set',
                    {'hunt_id': hunt_id, 'status': new_st},
                    actor_type='ui',
                    session_id=f'hunt_{hunt_id}',
                )
                if not result.success:
                    raise RuntimeError(result.error or 'Status update failed.')
                ui.notify(f"Hunt status updated to {new_st}. Undo is available.")
                render_grid()
            except Exception as e:
                ui.notify(f"Error: {e}", type="negative")

        def confirm_delete_hunt(hunt_id: int, title: str):
            approval_session = f"hunt_archive_{hunt_id}"
            requested = dispatch_preview(
                "hunts.archive",
                {"hunt_id": hunt_id},
                actor_type="ui",
                session_id=approval_session,
            )
            if not requested.success:
                ui.notify(requested.error or "Could not create archive preview.", type="negative")
                return
            pending = requested.data or {}
            preview = pending.get("preview") or {}
            with ui.dialog() as dialog, ui.card().classes('p-6 th-card border border-red-500/30 gap-4'):
                ui.label(f'Archive Campaign "{title}"?').classes('th-subheading text-slate-100')
                ui.label(preview.get("summary") or 'The campaign will leave active views.').classes('th-body text-slate-300')
                ui.label(
                    f'{preview.get("pipeline_candidates", 0)} pipeline enrollment(s) are affected. '
                    'The campaign can be restored from Action History for seven days.'
                ).classes('text-xs text-slate-400')
                with ui.row().classes('w-full justify-end gap-3'):
                    def cancel_archive():
                        cancel_approval(
                            int(pending["approval_id"]),
                            session_id=approval_session,
                        )
                        dialog.close()

                    ui.button('Cancel', on_click=cancel_archive).props('flat').classes('text-slate-400')
                    def do_del():
                        try:
                            result = approve_and_dispatch(
                                int(pending["approval_id"]),
                                session_id=approval_session,
                                actor_type="ui",
                            )
                            if not result.success:
                                raise RuntimeError(result.error or "Archive failed")
                            ui.notify(f'Campaign "{title}" archived. Undo is available for seven days.', type='info')
                            dialog.close()
                            render_grid()
                        except Exception as e:
                            ui.notify(f"Error: {e}", type="negative")
                    ui.button('Archive Campaign', color='red', on_click=do_del).classes('bg-red-600 text-white text-xs px-4 py-2 rounded')
            dialog.open()

        def open_edit_hunt_dialog(hunt_id: int):
            """Open edit dialog by hunt id (never pass a detached ORM row from the grid)."""
            try:
                with SessionFactory() as db:
                    fresh = get_hunt(db, int(hunt_id))
                    if not fresh:
                        ui.notify('Hunt not found', type='negative')
                        return
                    title0 = fresh.title or ""
                    role0 = fresh.target_role or ""
                    loc0 = fresh.location or ""
                    salary0 = fresh.salary_range or ""
                    desc0 = fresh.description or ""
                    sc = fresh.search_config
                    skills0 = (sc.required_skills if sc and sc.required_skills else "") or ""
                    industry0 = (sc.industry if sc and sc.industry else "") or ""
                    exp0 = ""
                    if sc:
                        emin = sc.experience_years_min
                        emax = sc.experience_years_max
                        if emin is not None and emax is not None:
                            exp0 = f"{emin}-{emax}" if emin != emax else str(emin)
                        elif emin is not None:
                            exp0 = f"{emin}+"
                        elif emax is not None:
                            exp0 = f"0-{emax}"
                    hid = fresh.id
            except Exception as e:
                ui.notify(f'Could not open editor: {e}', type='negative')
                return

            with ui.dialog() as dialog, ui.card().classes('w-full max-w-2xl p-6 th-card gap-4'):
                ui.label('Hunts / Edit').classes('th-ey')
                ui.label('Edit Talent Hunt').classes('th-title')
                ui.label(f'Update campaign details for “{title0}”.').classes('th-muted')

                title_in, role_in, loc_in, exp_in, salary_in, skills_in, industry_in, desc_in = _hunt_form_fields(
                    title=title0,
                    role=role0,
                    location=loc0,
                    experience=exp0,
                    salary=salary0,
                    skills=skills0,
                    industry=industry0,
                    description=desc0,
                )

                with ui.row().classes('w-full justify-end gap-3 mt-4'):
                    ui.button('Cancel', on_click=dialog.close).props('flat').classes('text-[#8195a5]')

                    def save():
                        if not title_in.value.strip():
                            ui.notify('Please provide a campaign title', type='negative')
                            return

                        try:
                            skills_text = (skills_in.value or "").strip() or None
                            industry_text = (industry_in.value or "").strip() or None
                            salary_text = (salary_in.value or "").strip() or None
                            loc_text = (loc_in.value or "").strip() or None
                            desc_text = (desc_in.value or "").strip() or None

                            result = dispatch_action(
                                'hunts.update',
                                {
                                    'hunt_id': hid,
                                    'title': title_in.value.strip(),
                                    'target_role': (role_in.value or '').strip() or None,
                                    'location': loc_text,
                                    'salary_range': salary_text,
                                    'description': desc_text,
                                    'required_skills': skills_text,
                                    'industry': industry_text,
                                    'experience': (exp_in.value or '').strip() or None,
                                },
                                actor_type='ui',
                                session_id=f'hunt_{hid}',
                            )
                            if not result.success:
                                raise RuntimeError(result.error or 'Hunt update failed.')

                            ui.notify('Talent Hunt updated. Undo is available.', type='positive')
                            dialog.close()
                            render_grid()
                        except Exception as e:
                            ui.notify(f"Error: {e}", type="negative")

                    ui.button('Save Changes', icon='save', on_click=save).classes('th-primary-btn')
            dialog.open()

        search_input.on('update:model-value', lambda e: render_grid())
        render_grid()


def hunts_page():
    create_layout(render_hunts)
