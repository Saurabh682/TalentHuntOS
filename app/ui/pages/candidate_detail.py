"""NiceGUI 360-degree view page for a single candidate profile."""

import json
from nicegui import ui
from app.ui.layout import create_layout
from app.infrastructure.db import SessionFactory, init_db
from app.candidates.service import (
    get_candidate,
    update_candidate,
    add_candidate_tag,
    remove_candidate_tag,
    add_candidate_note,
    add_candidate_experience,
    add_candidate_education,
)
from app.candidates.rag import candidate_rag


def render_candidate_detail(candidate_id: int):
    """Render 360-degree view for candidate ID."""
    init_db()

    with SessionFactory() as db:
        candidate = get_candidate(db, candidate_id)

        if not candidate:
            with ui.column().classes('w-full items-center justify-center p-12 gap-4'):
                ui.icon('error_outline', size='xl', color='red-500')
                ui.label(f'Candidate #{candidate_id} not found.').classes('text-xl text-slate-300')
                ui.button('Back to Candidates', icon='arrow_back', on_click=lambda: ui.navigate.to('/candidates')).classes('th-teal-btn')
            return

        with ui.column().classes('w-full gap-0'):
            # Top Navigation Header
            with ui.row().classes('w-full justify-between items-center mb-[22px]'):
                with ui.row().classes('items-center gap-3'):
                    ui.button(
                        icon='arrow_back', on_click=lambda: ui.navigate.to('/candidates')
                    ).props('flat round dense').classes('text-[#8195a5] hover:text-[#19d3c5]')
                    with ui.column().classes('gap-0'):
                        ui.label('Candidates / Profile').classes('th-ey')
                        ui.label(candidate.full_name or 'Candidate Profile').classes('th-title')
                        ui.label(f"ID #{candidate.id} · 360° profile").classes('th-muted')

                with ui.row().classes('items-center gap-2'):
                    ui.button('Edit Profile', icon='edit', on_click=lambda: open_edit_profile_dialog()).classes('th-slate-btn text-xs')
                    ui.button('Add Note', icon='post_add', on_click=lambda: open_add_note_dialog()).classes('th-primary-btn text-xs')

            # Main Profile Header Card
            with ui.card().classes('w-full p-6 th-card gap-4'):
                with ui.row().classes('w-full justify-between items-start flex-wrap gap-4'):
                    with ui.row().classes('items-center gap-5'):
                        ui.avatar(candidate.full_name[0].upper() if candidate.full_name else '?', color='teal-9', text_color='teal-2').classes('w-16 h-16 text-2xl font-bold border-2 border-teal-400/40')
                        with ui.column().classes('gap-1'):
                            with ui.row().classes('items-center gap-3'):
                                ui.label(candidate.full_name).classes('text-2xl font-bold text-slate-100')
                                st_color = 'teal' if candidate.status == 'Active' else ('amber' if candidate.status == 'Passive' else 'blue-grey')
                                ui.badge(candidate.status, color=st_color).classes('text-xs px-2.5 py-0.5')

                            ui.label(f"{candidate.current_title or 'Candidate'} at {candidate.current_company or 'N/A'}").classes('text-sm text-teal-300 font-medium')

                            with ui.row().classes('items-center gap-4 text-xs text-slate-400 mt-1 flex-wrap'):
                                if candidate.location:
                                    with ui.row().classes('items-center gap-1'):
                                        ui.icon('place', size='xs', color='amber-4')
                                        ui.label(candidate.location)
                                if candidate.experience_years:
                                    with ui.row().classes('items-center gap-1'):
                                        ui.icon('work_history', size='xs', color='teal-4')
                                        ui.label(f"{candidate.experience_years} Years Exp")
                                if candidate.email:
                                    with ui.row().classes('items-center gap-1'):
                                        ui.icon('email', size='xs', color='indigo-4')
                                        ui.label(candidate.email)
                                if candidate.phone:
                                    with ui.row().classes('items-center gap-1'):
                                        ui.icon('phone', size='xs', color='emerald-4')
                                        ui.label(candidate.phone)

                    # Social / Profile Links
                    with ui.row().classes('items-center gap-2'):
                        if candidate.linkedin_url:
                            ui.link('LinkedIn', target=candidate.linkedin_url, new_tab=True).classes('bg-slate-800 hover:bg-slate-700 text-teal-300 text-xs px-3 py-1.5 rounded-lg border border-teal-900/40')
                        if candidate.github_url:
                            ui.link('GitHub', target=candidate.github_url, new_tab=True).classes('bg-slate-800 hover:bg-slate-700 text-amber-300 text-xs px-3 py-1.5 rounded-lg border border-amber-900/40')
                        if candidate.portfolio_url:
                            ui.link('Portfolio', target=candidate.portfolio_url, new_tab=True).classes('bg-slate-800 hover:bg-slate-700 text-indigo-300 text-xs px-3 py-1.5 rounded-lg border border-indigo-900/40')

                # Headline & Summary
                if candidate.profile and (candidate.profile.headline or candidate.profile.summary):
                    ui.separator().classes('bg-teal-900/30 my-1')
                    with ui.column().classes('w-full gap-1'):
                        if candidate.profile.headline:
                            ui.label(candidate.profile.headline).classes('text-sm font-semibold text-slate-200')
                        if candidate.profile.summary:
                            ui.label(candidate.profile.summary).classes('text-xs text-slate-300 leading-relaxed')

            # Two-Column Content Grid
            with ui.row().classes('w-full gap-6 items-start'):
                # Left Column (2/3 width): Experiences, Education, Resume & RAG Q&A
                with ui.column().classes('col-12 col-lg-8 gap-6'):
                    # 1. Targeted AI RAG Q&A Box for this Candidate
                    with ui.card().classes('w-full p-5 th-card border border-indigo-500/30 gap-3'):
                        with ui.row().classes('items-center gap-2'):
                            ui.icon('psychology', size='sm', color='indigo-4')
                            ui.label('Ask Candidate AI Assistant').classes('text-base font-bold text-slate-100')
                            ui.badge('LlamaIndex RAG', color='indigo').classes('text-[10px]')

                        with ui.row().classes('w-full gap-2 items-center'):
                            cand_qa_input = ui.input(
                                placeholder=f'Ask anything about {candidate.full_name} (e.g. "Summarize core engineering strengths")'
                            ).classes('grow text-xs').props('dark outlined dense')
                            ui.button('Ask', icon='send', color='indigo', on_click=lambda: run_cand_qa()).classes('bg-indigo-600 hover:bg-indigo-500 text-white text-xs px-4 py-2 rounded')

                        qa_output_box = ui.column().classes('w-full p-3 bg-slate-950/70 border border-teal-900/30 rounded-md min-h-[60px]')
                        qa_output_box.set_visibility(False)

                    # 2. Work Experience Section
                    with ui.card().classes('w-full p-5 th-card border border-teal-900/30 gap-4'):
                        with ui.row().classes('w-full justify-between items-center'):
                            with ui.row().classes('items-center gap-2'):
                                ui.icon('work', size='sm', color='teal-4')
                                ui.label('Work Experience').classes('text-base font-bold text-slate-100')
                            ui.button('Add Experience', icon='add', on_click=lambda: open_add_exp_dialog()).props('flat dense').classes('text-xs text-teal-400')

                        if not candidate.experiences:
                            ui.label('No work experience entries recorded yet.').classes('text-xs text-slate-500 italic')
                        else:
                            with ui.column().classes('w-full gap-4'):
                                for exp in candidate.experiences:
                                    with ui.row().classes('w-full justify-between items-start border-l-2 border-teal-500 pl-4 py-1 gap-2'):
                                        with ui.column().classes('gap-0 grow'):
                                            ui.label(exp.title).classes('text-sm font-bold text-slate-100')
                                            ui.label(exp.company).classes('text-xs text-teal-300 font-medium')
                                            date_str = f"{exp.start_date or ''} - {'Present' if exp.is_current else (exp.end_date or '')}"
                                            ui.label(date_str).classes('text-[11px] text-slate-400')
                                            if exp.description:
                                                ui.label(exp.description).classes('text-xs text-slate-300 mt-1 line-clamp-3')

                    # 3. Education Section
                    with ui.card().classes('w-full p-5 th-card border border-teal-900/30 gap-4'):
                        with ui.row().classes('w-full justify-between items-center'):
                            with ui.row().classes('items-center gap-2'):
                                ui.icon('school', size='sm', color='amber-4')
                                ui.label('Education').classes('text-base font-bold text-slate-100')
                            ui.button('Add Education', icon='add', on_click=lambda: open_add_edu_dialog()).props('flat dense').classes('text-xs text-amber-400')

                        if not candidate.educations:
                            ui.label('No education entries recorded.').classes('text-xs text-slate-500 italic')
                        else:
                            with ui.column().classes('w-full gap-3'):
                                for edu in candidate.educations:
                                    with ui.row().classes('items-start border-l-2 border-amber-500 pl-4 py-1 gap-2'):
                                        with ui.column().classes('gap-0'):
                                            ui.label(edu.institution).classes('text-sm font-bold text-slate-100')
                                            deg_str = f"{edu.degree or ''} in {edu.field_of_study or ''}".strip(' in')
                                            ui.label(deg_str).classes('text-xs text-slate-300')
                                            yrs_str = f"{edu.start_year or ''} - {edu.end_year or ''}".strip(' -')
                                            if yrs_str:
                                                ui.label(yrs_str).classes('text-[11px] text-slate-400')

                    # 4. Resume Text Excerpt
                    if candidate.profile and candidate.profile.resume_text:
                        with ui.card().classes('w-full p-5 th-card border border-teal-900/30 gap-3'):
                            with ui.row().classes('items-center gap-2'):
                                ui.icon('description', size='sm', color='teal-4')
                                ui.label('Resume Text Excerpt').classes('text-base font-bold text-slate-100')
                            with ui.scroll_area().classes('w-full h-48 p-3 bg-slate-950/80 border border-teal-900/20 rounded-md'):
                                ui.label(candidate.profile.resume_text).classes('text-xs text-slate-300 whitespace-pre-wrap font-mono')

                # Right Column (1/3 width): Skills, Tags, AI Evaluation, Recruiter Notes
                with ui.column().classes('col-12 col-lg-4 gap-6'):
                    # AI Candidate Evaluation Card
                    if candidate.profile and candidate.profile.ai_evaluation:
                        with ui.card().classes('w-full p-5 th-card border border-teal-500/40 bg-teal-950/30 gap-2'):
                            with ui.row().classes('items-center gap-2'):
                                ui.icon('auto_awesome', size='sm', color='teal-3')
                                ui.label('AI Recruiter Evaluation').classes('text-sm font-bold text-teal-200')
                            ui.label(candidate.profile.ai_evaluation).classes('text-xs text-slate-200 leading-relaxed')

                    # Skills Card
                    skills_list = []
                    if candidate.profile and candidate.profile.skills_json:
                        try:
                            skills_list = json.loads(candidate.profile.skills_json)
                        except Exception:
                            skills_list = []

                    with ui.card().classes('w-full p-5 th-card border border-teal-900/30 gap-3'):
                        with ui.row().classes('items-center gap-2'):
                            ui.icon('psychology', size='sm', color='teal-4')
                            ui.label('Top Skills').classes('text-base font-bold text-slate-100')

                        if not skills_list:
                            ui.label('No skills listed.').classes('text-xs text-slate-500 italic')
                        else:
                            with ui.row().classes('gap-1.5 flex-wrap'):
                                for sk in skills_list:
                                    ui.badge(sk, color='slate-800').classes('text-xs text-teal-300 px-2.5 py-1 border border-teal-900/40 rounded-md')

                    # Candidate Tags Card
                    with ui.card().classes('w-full p-5 th-card border border-teal-900/30 gap-3'):
                        with ui.row().classes('w-full justify-between items-center'):
                            with ui.row().classes('items-center gap-2'):
                                ui.icon('sell', size='sm', color='indigo-4')
                                ui.label('CRM Tags').classes('text-base font-bold text-slate-100')
                            ui.button('Add Tag', icon='add', on_click=lambda: open_add_tag_dialog()).props('flat dense').classes('text-xs text-indigo-400')

                        if not candidate.tags:
                            ui.label('No CRM tags assigned.').classes('text-xs text-slate-500 italic')
                        else:
                            with ui.row().classes('gap-2 flex-wrap'):
                                for tg in candidate.tags:
                                    tag_id = tg.id
                                    with ui.chip(
                                        tg.tag_name,
                                        color='indigo-9',
                                        on_close=lambda e, tid=tag_id: handle_remove_tag(tid)
                                    ).classes('text-xs text-indigo-200'):
                                        pass

                    # Recruiter Notes Timeline Card
                    with ui.card().classes('w-full p-5 th-card border border-teal-900/30 gap-3'):
                        with ui.row().classes('items-center gap-2'):
                            ui.icon('notes', size='sm', color='teal-4')
                            ui.label('Recruiter Notes & Activity').classes('text-base font-bold text-slate-100')

                        # Quick Note Input
                        note_in = ui.input(placeholder='Type recruiter note and press Enter...').classes('w-full text-xs').props('dark outlined dense')

                        def post_quick_note():
                            if not note_in.value.strip():
                                return
                            with SessionFactory() as db:
                                add_candidate_note(db, candidate_id=candidate.id, content=note_in.value.strip())
                            ui.notify('Note added.', type='positive')
                            ui.navigate.to(f'/candidates/{candidate_id}')

                        note_in.on('keydown.enter', post_quick_note)

                        if not candidate.notes:
                            ui.label('No notes recorded yet.').classes('text-xs text-slate-500 italic')
                        else:
                            with ui.column().classes('w-full gap-3 mt-2'):
                                for n in candidate.notes:
                                    with ui.card().classes('w-full p-3 bg-slate-900/80 border border-teal-900/20 rounded-md gap-1'):
                                        with ui.row().classes('w-full justify-between items-center text-[10px] text-slate-400'):
                                            ui.label(n.author).classes('font-semibold text-teal-400')
                                            ui.label(n.created_at.strftime('%b %d, %H:%M'))
                                        ui.label(n.content).classes('text-xs text-slate-200')

    # Helper Dialog Functions
    def run_cand_qa():
        q_text = cand_qa_input.value.strip()
        if not q_text:
            return
        qa_output_box.set_visibility(True)
        qa_output_box.clear()
        with qa_output_box:
            with ui.row().classes('items-center gap-2 text-indigo-400 text-xs'):
                ui.spinner(size='sm', color='indigo')
                ui.label('Analyzing candidate profile...')

        with SessionFactory() as db:
            res = candidate_rag.ask_candidate_question(candidate_id=candidate_id, question=q_text, db=db)

        qa_output_box.clear()
        with qa_output_box:
            ui.label(f'Q: "{q_text}"').classes('text-[11px] font-bold text-indigo-300 mb-1')
            ui.markdown(res["answer"]).classes('text-xs text-slate-200 leading-relaxed')

    def handle_remove_tag(tag_id: int):
        with SessionFactory() as db:
            remove_candidate_tag(db, candidate_id, tag_id)
        ui.notify('Tag removed.', type='info')
        ui.navigate.to(f'/candidates/{candidate_id}')

    def open_add_tag_dialog():
        with ui.dialog() as dialog, ui.card().classes('p-6 th-card border border-indigo-500/40 gap-3'):
            ui.label('Add Candidate Tag').classes('text-lg font-bold text-slate-100')
            tag_input = ui.input('Tag Name', placeholder='e.g., Top Tier, Remote Only').classes('w-full').props('dark outlined dense')
            with ui.row().classes('w-full justify-end gap-2 mt-2'):
                ui.button('Cancel', on_click=dialog.close).props('flat').classes('text-slate-400')
                def save_t():
                    if tag_input.value.strip():
                        with SessionFactory() as db:
                            add_candidate_tag(db, candidate_id, tag_input.value.strip())
                        ui.notify('Tag added.', type='positive')
                        dialog.close()
                        ui.navigate.to(f'/candidates/{candidate_id}')
                ui.button('Add Tag', color='indigo', on_click=save_t).classes('bg-indigo-600 text-white text-xs px-3 py-1.5 rounded')
        dialog.open()

    def open_add_note_dialog():
        with ui.dialog() as dialog, ui.card().classes('w-full max-w-md p-6 th-card border border-teal-500/30 gap-3'):
            ui.label('Add Recruiter Note').classes('text-lg font-bold text-slate-100')
            author_in = ui.input('Author', value='Recruiter').classes('w-full').props('dark outlined dense')
            note_content_in = ui.textarea('Note Content').classes('w-full').props('dark outlined dense')
            with ui.row().classes('w-full justify-end gap-2 mt-2'):
                ui.button('Cancel', on_click=dialog.close).props('flat').classes('text-slate-400')
                def save_n():
                    if note_content_in.value.strip():
                        with SessionFactory() as db:
                            add_candidate_note(db, candidate_id, note_content_in.value.strip(), author=author_in.value.strip())
                        ui.notify('Note saved.', type='positive')
                        dialog.close()
                        ui.navigate.to(f'/candidates/{candidate_id}')
                ui.button('Save Note', icon='check', on_click=save_n).classes('th-teal-btn text-xs')
        dialog.open()

    def open_add_exp_dialog():
        with ui.dialog() as dialog, ui.card().classes('w-full max-w-md p-6 th-card border border-teal-500/30 gap-3'):
            ui.label('Add Work Experience').classes('text-lg font-bold text-slate-100')
            comp_in = ui.input('Company Name').classes('w-full').props('dark outlined dense')
            t_in = ui.input('Job Title').classes('w-full').props('dark outlined dense')
            start_in = ui.input('Start Date (e.g. 2021-01)').classes('w-full').props('dark outlined dense')
            end_in = ui.input('End Date (leave blank if current)').classes('w-full').props('dark outlined dense')
            curr_chk = ui.checkbox('Current Role', value=False).classes('text-slate-300 text-xs')
            desc_in = ui.textarea('Description').classes('w-full').props('dark outlined dense')

            with ui.row().classes('w-full justify-end gap-2 mt-2'):
                ui.button('Cancel', on_click=dialog.close).props('flat').classes('text-slate-400')
                def save_e():
                    if comp_in.value.strip() and t_in.value.strip():
                        with SessionFactory() as db:
                            add_candidate_experience(
                                db, candidate_id=candidate_id,
                                company=comp_in.value.strip(),
                                title=t_in.value.strip(),
                                start_date=start_in.value.strip() or None,
                                end_date=end_in.value.strip() or None,
                                is_current=curr_chk.value,
                                description=desc_in.value.strip() or None
                            )
                        ui.notify('Experience added.', type='positive')
                        dialog.close()
                        ui.navigate.to(f'/candidates/{candidate_id}')
                ui.button('Save Experience', icon='check', on_click=save_e).classes('th-teal-btn text-xs')
        dialog.open()

    def open_add_edu_dialog():
        with ui.dialog() as dialog, ui.card().classes('w-full max-w-md p-6 th-card border border-amber-500/30 gap-3'):
            ui.label('Add Education Record').classes('text-lg font-bold text-slate-100')
            inst_in = ui.input('Institution / University').classes('w-full').props('dark outlined dense')
            deg_in = ui.input('Degree (e.g., M.S., B.S.)').classes('w-full').props('dark outlined dense')
            field_in = ui.input('Field of Study').classes('w-full').props('dark outlined dense')
            s_yr = ui.number('Start Year', value=2015).classes('w-full').props('dark outlined dense')
            e_yr = ui.number('End Year', value=2019).classes('w-full').props('dark outlined dense')

            with ui.row().classes('w-full justify-end gap-2 mt-2'):
                ui.button('Cancel', on_click=dialog.close).props('flat').classes('text-slate-400')
                def save_edu():
                    if inst_in.value.strip():
                        with SessionFactory() as db:
                            add_candidate_education(
                                db, candidate_id=candidate_id,
                                institution=inst_in.value.strip(),
                                degree=deg_in.value.strip() or None,
                                field_of_study=field_in.value.strip() or None,
                                start_year=int(s_yr.value) if s_yr.value else None,
                                end_year=int(e_yr.value) if e_yr.value else None,
                            )
                        ui.notify('Education added.', type='positive')
                        dialog.close()
                        ui.navigate.to(f'/candidates/{candidate_id}')
                ui.button('Save Education', icon='check', on_click=save_edu).classes('bg-amber-600 hover:bg-amber-500 text-white text-xs px-3 py-1.5 rounded')
        dialog.open()

    def open_edit_profile_dialog():
        with ui.dialog() as dialog, ui.card().classes('w-full max-w-lg p-6 th-card border border-teal-500/30 gap-3'):
            ui.label('Edit Candidate Details').classes('text-xl font-bold text-slate-100')
            with SessionFactory() as db:
                from app.candidates.models import Candidate
                cand = db.get(Candidate, candidate_id)
                fn_val = cand.full_name if cand else ''
                title_val = cand.current_title if cand else ''
                comp_val = cand.current_company if cand else ''
                loc_val = cand.location if cand else ''
                head_val = cand.profile.headline if cand and cand.profile else ''
                sum_val = cand.profile.summary if cand and cand.profile else ''

            fn_in = ui.input('Full Name', value=fn_val).classes('w-full').props('dark outlined dense')
            title_in = ui.input('Current Title', value=title_val).classes('w-full').props('dark outlined dense')
            comp_in = ui.input('Current Company', value=comp_val).classes('w-full').props('dark outlined dense')
            loc_in = ui.input('Location', value=loc_val).classes('w-full').props('dark outlined dense')
            head_in = ui.input('Headline', value=head_val).classes('w-full').props('dark outlined dense')
            sum_in = ui.textarea('Summary', value=sum_val).classes('w-full').props('dark outlined dense')

            with ui.row().classes('w-full justify-end gap-2 mt-3'):
                ui.button('Cancel', on_click=dialog.close).props('flat').classes('text-slate-400')
                def save_profile():
                    with SessionFactory() as db:
                        update_candidate(
                            db, candidate_id=candidate_id,
                            full_name=fn_in.value.strip(),
                            current_title=title_in.value.strip() or None,
                            current_company=comp_in.value.strip() or None,
                            location=loc_in.value.strip() or None,
                            headline=head_in.value.strip() or None,
                            summary=sum_in.value.strip() or None,
                        )
                    ui.notify('Profile updated.', type='positive')
                    dialog.close()
                    ui.navigate.to(f'/candidates/{candidate_id}')
                ui.button('Update Profile', icon='save', on_click=save_profile).classes('th-teal-btn text-xs')
        dialog.open()


def candidate_detail_page(candidate_id: int):
    create_layout(lambda: render_candidate_detail(candidate_id))
