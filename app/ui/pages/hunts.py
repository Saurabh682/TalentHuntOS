"""NiceGUI Talent Hunts Campaign Management Page."""

from nicegui import ui
from app.ui.layout import create_layout
from app.infrastructure.db import SessionFactory, init_db
from app.hunts.service import create_hunt, list_hunts, get_hunt, get_hunt_metrics, update_hunt, delete_hunt
from app.hunts.experience import parse_experience_range
from app.hunts.models import HuntSearchConfig


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
            ui.label('Salary Range').classes('th-caption')
            salary_in = ui.input(
                value=salary,
                placeholder='e.g., ₹15–25 LPA',
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
                                with ui.column().classes('items-center gap-0 cursor-pointer hover:opacity-80 transition-opacity').on('click', lambda e: ui.navigate.to('/candidates')):
                                    ui.label(str(metrics.get("total_candidates", 0))).classes('text-lg font-bold text-[#19d3c5]')
                                    ui.label('Candidates').classes('text-[10px] text-[#8195a5]')
                                
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
                                        on_click=lambda e, h=hunt: open_edit_hunt_dialog(h)
                                    ).props('flat round dense').classes('text-[#8195a5] hover:text-[#19d3c5]').tooltip('Edit Campaign')

                                    ui.button(
                                        icon='auto_awesome',
                                        on_click=lambda e, hid=hunt.id, t=hunt.title: trigger_ai_sourcing(hid, t)
                                    ).props('flat round dense').classes('text-[#8195a5] hover:text-[#19d3c5]').tooltip('AI Auto-Pilot Sourcing')

                                    toggle_icon = 'pause' if hunt.status == 'Active' else 'play_arrow'
                                    ui.button(
                                        icon=toggle_icon,
                                        on_click=lambda e, hid=hunt.id, st=hunt.status: toggle_hunt_status(hid, st)
                                    ).props('flat round dense').classes('text-[#8195a5] hover:text-[#edf5f7]').tooltip('Pause / Resume Campaign')

                                    ui.button(
                                        icon='delete_outline',
                                        on_click=lambda e, hid=hunt.id, t=hunt.title: confirm_delete_hunt(hid, t)
                                    ).props('flat round dense').classes('text-[#8195a5] hover:text-red-400').tooltip('Delete Talent Hunt')

        render_grid_ref["fn"] = render_grid

        def set_filter(status_name):
            selected_status["value"] = status_name
            render_grid()

        def trigger_ai_sourcing(hunt_id: int, title: str):
            try:
                from app.intelligence.auto_pilot import run_autopilot_hunt_job
                ui.notify(f"AI Auto-Pilot sourcing candidates for '{title}'...", type="info")
                res = run_autopilot_hunt_job(hunt_id)
                ui.notify(f"Sourcing finished: {res.get('candidates_sourced', 0)} candidates matched!", type="positive")
                render_grid()
            except Exception as e:
                ui.notify(f"Auto-pilot error: {e}", type="negative")

        def toggle_hunt_status(hunt_id, current_status):
            try:
                new_st = 'Paused' if current_status == 'Active' else 'Active'
                with SessionFactory() as db:
                    update_hunt(db, hunt_id, status=new_st)
                ui.notify(f"Hunt status updated to {new_st}")
                render_grid()
            except Exception as e:
                ui.notify(f"Error: {e}", type="negative")

        def confirm_delete_hunt(hunt_id: int, title: str):
            with ui.dialog() as dialog, ui.card().classes('p-6 th-card border border-red-500/30 gap-4'):
                ui.label(f'Delete Campaign "{title}"?').classes('th-subheading text-slate-100')
                ui.label('This will permanently delete this Talent Hunt campaign, pipeline stages, and candidate enrollments.').classes('th-body text-slate-400')
                with ui.row().classes('w-full justify-end gap-3'):
                    ui.button('Cancel', on_click=dialog.close).props('flat').classes('text-slate-400')
                    def do_del():
                        try:
                            with SessionFactory() as db:
                                delete_hunt(db, hunt_id)
                            ui.notify(f'Campaign "{title}" deleted.', type='info')
                            dialog.close()
                            render_grid()
                        except Exception as e:
                            ui.notify(f"Error: {e}", type="negative")
                    ui.button('Delete Campaign', color='red', on_click=do_del).classes('bg-red-600 text-white text-xs px-4 py-2 rounded')
            dialog.open()

        def open_edit_hunt_dialog(hunt):
            # Reload so we show current fields (same set as Create)
            with SessionFactory() as db:
                fresh = get_hunt(db, hunt.id) or hunt
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
                hunt_id = fresh.id

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
                            emin, emax = parse_experience_range(exp_in.value)
                            skills_text = (skills_in.value or "").strip() or None
                            industry_text = (industry_in.value or "").strip() or None
                            salary_text = (salary_in.value or "").strip() or None
                            loc_text = (loc_in.value or "").strip() or None
                            desc_text = (desc_in.value or "").strip() or None

                            with SessionFactory() as db:
                                h = get_hunt(db, hunt_id)
                                if h is None:
                                    ui.notify('Hunt not found', type='negative')
                                    return
                                h.title = title_in.value.strip()
                                h.target_role = (role_in.value or "").strip() or None
                                h.location = loc_text
                                h.salary_range = salary_text
                                h.description = desc_text
                                if not h.search_config:
                                    h.search_config = HuntSearchConfig(hunt_id=h.id)
                                    db.add(h.search_config)
                                h.search_config.required_skills = skills_text
                                h.search_config.industry = industry_text
                                h.search_config.experience_years_min = emin
                                h.search_config.experience_years_max = emax
                                if loc_text:
                                    h.search_config.locations = loc_text
                                db.commit()

                            ui.notify('Talent Hunt updated!', type='positive')
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
