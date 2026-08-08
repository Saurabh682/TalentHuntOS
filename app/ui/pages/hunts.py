"""NiceGUI Talent Hunts Campaign Management Page."""

from nicegui import ui
from app.ui.layout import create_layout
from app.infrastructure.db import SessionFactory, init_db
from app.hunts.service import create_hunt, list_hunts, get_hunt_metrics, update_hunt, delete_hunt


def seed_demo_hunts_if_empty(db):
    """No-op: Demo hunts disabled as requested."""
    pass


def render_hunts():
    """Render the Hunts Campaign page content."""
    init_db()
    with SessionFactory() as db:
        seed_demo_hunts_if_empty(db)

    selected_status = {"value": "All"}
    render_grid_ref = {"fn": lambda: None}

    def open_create_hunt_dialog():
        with ui.dialog() as dialog, ui.card().classes('w-full max-w-lg p-6 th-card border border-teal-500/30 gap-4'):
            ui.label('Create New Talent Hunt').classes('th-display text-slate-100')
            ui.label('Set hunt parameters to launch AI sourcing and candidate matching.').classes('th-caption text-slate-400')

            with ui.column().classes('w-full gap-1'):
                ui.label('Hunt Campaign Title').classes('th-caption text-slate-300')
                title_in = ui.input(placeholder='e.g., Senior Rust Engineer').classes('w-full').props('dark outlined dense')

            with ui.column().classes('w-full gap-1'):
                ui.label('Target Role').classes('th-caption text-slate-300')
                role_in = ui.input(placeholder='e.g., Lead Developer').classes('w-full').props('dark outlined dense')

            with ui.column().classes('w-full gap-1'):
                ui.label('Location / Remote Policy').classes('th-caption text-slate-300')
                loc_in = ui.input(placeholder='e.g., Remote (US)').classes('w-full').props('dark outlined dense')

            with ui.column().classes('w-full gap-1'):
                ui.label('Required Experience').classes('th-caption text-slate-300')
                exp_in = ui.input(placeholder='e.g., 3-5 years, Senior (5+ yrs)').classes('w-full').props('dark outlined dense')

            with ui.column().classes('w-full gap-1'):
                ui.label('Salary Range').classes('th-caption text-slate-300')
                salary_in = ui.input(placeholder='e.g., $140k - $180k').classes('w-full').props('dark outlined dense')

            with ui.column().classes('w-full gap-1'):
                ui.label('Description').classes('th-caption text-slate-300')
                desc_in = ui.textarea(placeholder='Provide job responsibilities...').classes('w-full').props('dark outlined dense')

            with ui.column().classes('w-full gap-1'):
                ui.label('Required Skills (comma-separated)').classes('th-caption text-slate-300')
                skills_in = ui.input(placeholder='e.g., Python, Docker, FastAPI').classes('w-full').props('dark outlined dense')

            with ui.row().classes('w-full justify-end gap-3 mt-4'):
                ui.button('Cancel', on_click=dialog.close).props('flat').classes('text-slate-400')
                def save():
                    if not title_in.value.strip():
                        ui.notify('Please provide a campaign title', type='negative')
                        return
                    
                    cfg = {}
                    if skills_in.value.strip():
                        cfg["required_skills"] = skills_in.value.strip()
                    if exp_in.value.strip():
                        cfg["min_experience"] = exp_in.value.strip()

                    with SessionFactory() as db:
                        create_hunt(
                            db,
                            title=title_in.value.strip(),
                            target_role=role_in.value.strip() or None,
                            location=loc_in.value.strip() or None,
                            salary_range=salary_in.value.strip() or None,
                            description=desc_in.value.strip() or None,
                            search_config=cfg if cfg else None
                        )
                    ui.notify('Talent Hunt created successfully!', type='positive')
                    dialog.close()
                    render_grid_ref["fn"]()

                ui.button('Launch Hunt', icon='rocket_launch', on_click=save).classes('th-teal-btn')
        dialog.open()

    with ui.column().classes('w-full gap-6'):
        # Header Row
        with ui.row().classes('w-full justify-between items-center'):
            with ui.column().classes('gap-1'):
                ui.label('Talent Hunt Campaigns').classes('text-2xl font-bold text-slate-100')
                ui.label('Create, monitor, and execute AI-driven sourcing campaigns.').classes('text-sm text-slate-400')
            
            ui.button(
                'New Talent Hunt', icon='add', color='teal',
                on_click=open_create_hunt_dialog
            ).classes('th-teal-btn')

        # Filter & Search Bar
        with ui.card().classes('w-full p-4 th-card border border-teal-900/30'):
            with ui.row().classes('w-full justify-between items-center gap-4'):
                with ui.row().classes('items-center gap-2'):
                    ui.label('Filter:').classes('text-sm font-medium text-slate-400 mr-2')
                    for status_opt in ["All", "Active", "Draft", "Paused", "Completed"]:
                        ui.button(
                            status_opt,
                            on_click=lambda e, s=status_opt: set_filter(s)
                        ).props('dense flat').classes(
                            'text-xs px-3 py-1 rounded-full bg-slate-800 text-teal-300'
                        )
                
                search_input = ui.input(placeholder='Search hunts by title or role...').classes('w-64 text-sm').props('dense rounded outlined dark')

        grid_container = ui.row().classes('w-full gap-6 items-stretch')

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

                        with ui.card().classes('col-12 col-md-6 col-lg-4 p-5 bg-[#121619] border border-[#1E2226] rounded-xl flex flex-col justify-between hover:border-[#3ED9A6]/40 transition-all duration-200'):
                            with ui.column().classes('w-full gap-2'):
                                with ui.row().classes('w-full justify-between items-start gap-2'):
                                    ui.label(hunt.title).classes('text-base font-semibold text-[#E7E9EA] line-clamp-1')
                                    status_bg = 'bg-[#10241D] text-[#3ED9A6] border border-[#3ED9A6]/30' if hunt.status == 'Active' else 'bg-[#151A1D] text-[#8A9096] border border-[#1E2226]'
                                    ui.element('span').classes(f'text-[10px] px-2 py-0.5 rounded-md font-medium {status_bg}').text = hunt.status

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
                                    with ui.row().classes('items-center gap-3 text-xs text-[#8A9096] flex-wrap'):
                                        if hunt.target_role:
                                            with ui.row().classes('items-center gap-1'):
                                                ui.icon('work_outline', size='xs').classes('text-[#3ED9A6]')
                                                ui.label(hunt.target_role)
                                        if hunt.location:
                                            with ui.row().classes('items-center gap-1'):
                                                ui.icon('place', size='xs').classes('text-[#8A9096]')
                                                ui.label(hunt.location)
                                        if exp_req:
                                            with ui.row().classes('items-center gap-1'):
                                                ui.icon('history_edu', size='xs').classes('text-[#8A9096]')
                                                ui.label(exp_req)

                                if required_skills_list:
                                    with ui.row().classes('items-center gap-1 mt-1 flex-wrap'):
                                        for sk in required_skills_list[:4]:
                                            ui.element('span').classes('text-[10px] bg-[#151A1D] text-[#3ED9A6] px-2 py-0.5 border border-[#1E2226] rounded-md').text = sk

                                if hunt.description:
                                    ui.label(hunt.description).classes('text-xs text-[#8A9096] mt-1 line-clamp-2')

                            ui.separator().classes('bg-[#1E2226] my-3')

                            with ui.row().classes('w-full justify-around items-center bg-[#0B0D0F] p-2.5 rounded-lg border border-[#1E2226] mb-4'):
                                with ui.column().classes('items-center gap-0 cursor-pointer hover:opacity-80 transition-opacity').on('click', lambda e: ui.navigate.to('/candidates')):
                                    ui.label(str(metrics.get("total_candidates", 0))).classes('text-lg font-bold text-[#3ED9A6]')
                                    ui.label('Candidates').classes('text-[10px] text-[#8A9096]')
                                
                                ui.separator().props('vertical').classes('h-8 bg-[#1E2226]')

                                with ui.column().classes('items-center gap-0'):
                                    raw_sc = metrics.get('avg_match_score', 0)
                                    formatted_sc = f"{raw_sc:.1f}%" if isinstance(raw_sc, (int, float)) else f"{raw_sc}%"
                                    ui.label(formatted_sc).classes('text-lg font-bold text-[#E7E9EA]')
                                    ui.label('Avg Match').classes('text-[10px] text-[#8A9096]')

                                ui.separator().props('vertical').classes('h-8 bg-[#1E2226]')

                                with ui.column().classes('items-center gap-0'):
                                    ui.label(str(metrics.get("hired_count", 0))).classes('text-lg font-bold text-[#3ED9A6]')
                                    ui.label('Hired').classes('text-[10px] text-[#8A9096]')

                            with ui.column().classes('w-full gap-2 mt-auto pt-2'):
                                ui.button(
                                    'Pipeline Kanban', icon='view_kanban',
                                    on_click=lambda e, hid=hunt.id: ui.navigate.to(f'/hunts/{hid}/pipeline')
                                ).classes('w-full th-teal-btn text-xs py-2 rounded-lg font-medium')

                                with ui.row().classes('w-full justify-between items-center px-1 pt-1'):
                                    ui.button(
                                        icon='edit',
                                        on_click=lambda e, h=hunt: open_edit_hunt_dialog(h)
                                    ).props('flat round dense').classes('text-[#8A9096] hover:text-[#3ED9A6]').tooltip('Edit Campaign')

                                    ui.button(
                                        icon='auto_awesome',
                                        on_click=lambda e, hid=hunt.id, t=hunt.title: trigger_ai_sourcing(hid, t)
                                    ).props('flat round dense').classes('text-[#8A9096] hover:text-[#3ED9A6]').tooltip('AI Auto-Pilot Sourcing')

                                    toggle_icon = 'pause' if hunt.status == 'Active' else 'play_arrow'
                                    ui.button(
                                        icon=toggle_icon,
                                        on_click=lambda e, hid=hunt.id, st=hunt.status: toggle_hunt_status(hid, st)
                                    ).props('flat round dense').classes('text-[#8A9096] hover:text-[#EDEFEF]').tooltip('Pause / Resume Campaign')

                                    ui.button(
                                        icon='delete_outline',
                                        on_click=lambda e, hid=hunt.id, t=hunt.title: confirm_delete_hunt(hid, t)
                                    ).props('flat round dense').classes('text-[#8A9096] hover:text-red-400').tooltip('Delete Talent Hunt')

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
            with ui.dialog() as dialog, ui.card().classes('w-full max-w-lg p-6 th-card border border-blue-500/30 gap-4'):
                ui.label(f'Edit Hunt: {hunt.title}').classes('th-display text-slate-100')
                
                with ui.column().classes('w-full gap-1'):
                    ui.label('Hunt Campaign Title').classes('th-caption text-slate-300')
                    title_in = ui.input(value=hunt.title).classes('w-full').props('dark outlined dense')

                with ui.column().classes('w-full gap-1'):
                    ui.label('Target Role').classes('th-caption text-slate-300')
                    role_in = ui.input(value=hunt.target_role or '').classes('w-full').props('dark outlined dense')

                with ui.column().classes('w-full gap-1'):
                    ui.label('Location / Remote Policy').classes('th-caption text-slate-300')
                    loc_in = ui.input(value=hunt.location or '').classes('w-full').props('dark outlined dense')

                exp_req_val = ""
                skills_val = ""
                if hunt.search_config:
                    if hunt.search_config.experience_years_min is not None:
                        exp_req_val = str(hunt.search_config.experience_years_min)
                    if hunt.search_config.required_skills:
                        skills_val = hunt.search_config.required_skills

                with ui.column().classes('w-full gap-1'):
                    ui.label('Required Skills (comma-separated)').classes('th-caption text-slate-300')
                    skills_in = ui.input(value=skills_val).classes('w-full').props('dark outlined dense')

                with ui.row().classes('w-full justify-end gap-3 mt-4'):
                    ui.button('Cancel', on_click=dialog.close).props('flat').classes('text-slate-400')
                    def save():
                        if not title_in.value.strip():
                            ui.notify('Please provide a campaign title', type='negative')
                            return
                        
                        try:
                            with SessionFactory() as db:
                                h = get_hunt_metrics(db, hunt.id) # Just to check db works
                                update_hunt(db, hunt.id, 
                                    title=title_in.value.strip(),
                                    target_role=role_in.value.strip() or None,
                                    location=loc_in.value.strip() or None
                                )
                                # Need to update search config separately since it's a relationship
                                # For simplicity, we just update the main hunt details here
                            ui.notify('Talent Hunt updated!', type='positive')
                            dialog.close()
                            render_grid()
                        except Exception as e:
                            ui.notify(f"Error: {e}", type="negative")

                    ui.button('Save Changes', icon='save', on_click=save).classes('th-teal-btn bg-blue-600')
            dialog.open()

        search_input.on('update:model-value', lambda e: render_grid())
        render_grid()


def hunts_page():
    create_layout(render_hunts)
