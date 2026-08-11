"""NiceGUI 360-degree view page for a single candidate profile."""

import json
from nicegui import ui
from app.actions.api import dispatch_action
from app.ui.layout import create_layout
from app.infrastructure.db import SessionFactory, init_db
from app.candidates.service import (
    get_candidate,
)
from app.candidates.rag import candidate_rag
from app.candidates.intake_service import (
    create_intake_request,
    draft_outreach_message,
    get_latest_intake_status,
    get_hunt_jd_context,
    intake_url_for_token,
    apply_intake_submission,
    list_pending_submissions,
)
from app.ui.components.profile_review_dialog import (
    open_profile_sections_review,
    run_extract_then_review,
)


def render_candidate_detail(candidate_id: int):
    """Render 360-degree view for candidate ID."""
    init_db()

    def update_candidate_via_action(**changes):
        result = dispatch_action(
            "candidates.update",
            {"candidate_id": candidate_id, **changes},
            actor_type="ui",
            session_id=f"candidate_{candidate_id}",
        )
        if not result.success:
            raise RuntimeError(result.error or "Candidate update failed.")
        return result.data or {}

    with SessionFactory() as db:
        candidate = get_candidate(db, candidate_id)
        intake_status = get_latest_intake_status(db, candidate_id) if candidate else {}
        pending_subs = list_pending_submissions(db, candidate_id=candidate_id, limit=5) if candidate else []

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
                        with ui.row().classes('items-center gap-2'):
                            ui.label(f"ID #{candidate.id} · 360° profile").classes('th-muted')
                            if intake_status.get("status") and intake_status.get("status") != "none":
                                ui.badge(intake_status.get("label") or "", color="orange").classes("text-[10px]")

                with ui.row().classes('items-center gap-2 flex-wrap justify-end'):
                    ui.button('Edit Profile', icon='edit', on_click=lambda: open_edit_profile_dialog()).classes('th-slate-btn text-xs')
                    profile_url = candidate.linkedin_url or candidate.portfolio_url or candidate.github_url
                    if profile_url:
                        ui.button(
                            'Open & read page',
                            icon='travel_explore',
                            on_click=lambda u=profile_url: open_read_page_dialog(u),
                        ).props('flat dense').classes('text-xs text-teal-300')
                    ui.button(
                        'Send profile form',
                        icon='link',
                        on_click=lambda: open_send_intake_dialog(),
                    ).props('flat dense').classes('text-xs text-amber-300')
                    ui.button('Add Note', icon='post_add', on_click=lambda: open_add_note_dialog()).classes('th-primary-btn text-xs')

            if pending_subs:
                with ui.card().classes(
                    'w-full p-4 mb-4 th-card border border-orange-500/50 bg-orange-950/30 gap-2'
                ):
                    with ui.row().classes('w-full justify-between items-center flex-wrap gap-2'):
                        with ui.column().classes('gap-0'):
                            ui.label('Candidate form submitted — review required').classes(
                                'text-sm font-semibold text-orange-100'
                            )
                            ui.label(
                                'Accept to fill Experience / Education / Skills from their answers.'
                            ).classes('text-xs text-orange-200/80')
                        ui.button(
                            'Review candidate form',
                            icon='rate_review',
                            on_click=lambda sid=pending_subs[0]["submission_id"], p=pending_subs[0].get("payload") or {}: open_intake_review(sid, p),
                        ).classes('th-primary-btn text-xs')

            # Main Profile Header Card
            with ui.card().classes('w-full p-6 th-card gap-4'):
                with ui.row().classes('w-full justify-between items-start flex-wrap gap-4'):
                    with ui.row().classes('items-center gap-5'):
                        if candidate.profile_image_url:
                            ui.image(candidate.profile_image_url).classes(
                                'w-16 h-16 rounded-full object-cover border-2 border-teal-400/40'
                            )
                        else:
                            ui.avatar(candidate.full_name[0].upper() if candidate.full_name else '?', color='teal-9', text_color='teal-2').classes('w-16 h-16 text-2xl font-bold border-2 border-teal-400/40')
                        with ui.column().classes('gap-1'):
                            with ui.row().classes('items-center gap-3'):
                                ui.label(candidate.full_name).classes('text-2xl font-bold text-slate-100')
                                if candidate.pronouns:
                                    ui.label(candidate.pronouns).classes('text-xs text-slate-400')
                                if candidate.connection_degree:
                                    ui.badge(candidate.connection_degree, color='blue-grey').classes('text-[10px]')
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
                                if candidate.connections_count is not None:
                                    with ui.row().classes('items-center gap-1'):
                                        ui.icon('group', size='xs', color='blue-4')
                                        ui.label(f"{candidate.connections_count}+ connections")

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
                    highlights = []
                    if candidate.profile.highlights_json:
                        try:
                            highlights = json.loads(candidate.profile.highlights_json) or []
                        except Exception:
                            highlights = []
                    if highlights:
                        ui.separator().classes('bg-teal-900/30 my-1')
                        with ui.column().classes('w-full gap-1'):
                            ui.label('LinkedIn Highlights').classes('text-xs font-semibold text-amber-300')
                            for item in highlights:
                                ui.label(str(item)).classes('text-xs text-slate-300')

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
                            with ui.row().classes('items-center gap-1'):
                                ui.button(
                                    'Fill from page',
                                    icon='auto_fix_fix',
                                    on_click=lambda: open_fill_from_page_dialog(),
                                ).props('flat dense').classes('text-xs text-teal-300')
                                ui.button(
                                    'Paste text',
                                    icon='content_paste',
                                    on_click=lambda: open_paste_extract_dialog(),
                                ).props('flat dense').classes('text-xs text-slate-300')
                                ui.button(
                                    'Upload resume',
                                    icon='upload_file',
                                    on_click=lambda: open_resume_upload_dialog(),
                                ).props('flat dense').classes('text-xs text-slate-300')
                                ui.button('Add Experience', icon='add', on_click=lambda: open_add_exp_dialog()).props('flat dense').classes('text-xs text-teal-400')

                        if not candidate.experiences:
                            with ui.column().classes('w-full gap-2 py-2'):
                                ui.label('No work experience entries recorded yet.').classes('text-xs text-slate-500 italic')
                                ui.label(
                                    'Use Fill from page, Paste resume text, or Send profile form to the candidate.'
                                ).classes('text-[11px] text-slate-500')
                        else:
                            with ui.column().classes('w-full gap-4'):
                                for exp in candidate.experiences:
                                    with ui.row().classes('w-full justify-between items-start border-l-2 border-teal-500 pl-4 py-1 gap-2'):
                                        with ui.column().classes('gap-0 grow'):
                                            ui.label(exp.title).classes('text-sm font-bold text-slate-100')
                                            ui.label(exp.company).classes('text-xs text-teal-300 font-medium')
                                            date_str = f"{exp.start_date or ''} - {'Present' if exp.is_current else (exp.end_date or '')}"
                                            if exp.employment_type:
                                                date_str = f"{date_str} · {exp.employment_type}"
                                            ui.label(date_str).classes('text-[11px] text-slate-400')
                                            if exp.location:
                                                ui.label(exp.location).classes('text-[11px] text-slate-500')
                                            if exp.description:
                                                ui.label(exp.description).classes('text-xs text-slate-300 mt-1 line-clamp-3')
                                            if exp.skills_json:
                                                try:
                                                    role_skills = json.loads(exp.skills_json) or []
                                                except Exception:
                                                    role_skills = []
                                                if role_skills:
                                                    ui.label(' · '.join(role_skills)).classes('text-[11px] text-teal-300')

                    # 3. Education Section
                    with ui.card().classes('w-full p-5 th-card border border-teal-900/30 gap-4'):
                        with ui.row().classes('w-full justify-between items-center'):
                            with ui.row().classes('items-center gap-2'):
                                ui.icon('school', size='sm', color='amber-4')
                                ui.label('Education').classes('text-base font-bold text-slate-100')
                            with ui.row().classes('items-center gap-1'):
                                ui.button(
                                    'Paste text',
                                    icon='content_paste',
                                    on_click=lambda: open_paste_extract_dialog(),
                                ).props('flat dense').classes('text-xs text-slate-300')
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
                                            if edu.grade:
                                                ui.label(f"Grade: {edu.grade}").classes('text-[11px] text-slate-400')
                                            if edu.activities:
                                                ui.label(edu.activities).classes('text-[11px] text-slate-400')
                                            if edu.description:
                                                ui.label(edu.description).classes('text-[11px] text-slate-300')

                    # 4. Resume Text Excerpt
                    if candidate.profile and candidate.profile.resume_text:
                        with ui.card().classes('w-full p-5 th-card border border-teal-900/30 gap-3'):
                            with ui.row().classes('items-center gap-2'):
                                ui.icon('description', size='sm', color='teal-4')
                                ui.label('Resume Text Excerpt').classes('text-base font-bold text-slate-100')
                            with ui.scroll_area().classes('w-full h-48 p-3 bg-slate-950/80 border border-teal-900/20 rounded-md'):
                                ui.label(candidate.profile.resume_text).classes('text-xs text-slate-300 whitespace-pre-wrap font-mono')

                    # 5. Saved page snapshots (free Playwright local files)
                    from app.browser.snapshots import list_snapshots_for_candidate, resolve_data_path
                    snaps = list_snapshots_for_candidate(candidate_id)
                    if snaps:
                        with ui.card().classes('w-full p-5 th-card border border-teal-900/30 gap-3'):
                            with ui.row().classes('items-center gap-2'):
                                ui.icon('photo_camera', size='sm', color='teal-4')
                                ui.label('Page snapshots').classes('text-base font-bold text-slate-100')
                                ui.badge(f'{len(snaps)}', color='teal').classes('text-[10px]')
                            latest = snaps[0]
                            shot_rel = latest.get("screenshot_path") or ""
                            if shot_rel:
                                shot_url = shot_rel.replace('\\', '/').removeprefix('profile_snapshots/')
                                ui.image(f'/profile-snapshots/{shot_url}').classes(
                                    'w-full max-h-80 object-contain rounded border border-teal-900/40 bg-slate-950'
                                )
                            with ui.column().classes('w-full gap-1'):
                                if latest.get("source_url"):
                                    ui.label(latest["source_url"]).classes('text-[11px] text-teal-400 break-all')
                                if latest.get("created_at"):
                                    ui.label(f'Saved {latest["created_at"]}').classes('text-[11px] text-slate-500')
                                txt_rel = latest.get("text_path") or ""
                                if txt_rel:
                                    try:
                                        preview = resolve_data_path(txt_rel).read_text(
                                            encoding="utf-8", errors="replace"
                                        )[:2500]
                                    except Exception:
                                        preview = ""
                                    if preview:
                                        with ui.expansion('Snapshot text', icon='article').classes('w-full text-xs'):
                                            ui.label(preview).classes(
                                                'text-[11px] text-slate-300 whitespace-pre-wrap font-mono'
                                            )
                                if len(snaps) > 1:
                                    ui.label(f'+ {len(snaps) - 1} older snapshot(s) on disk').classes(
                                        'text-[11px] text-slate-500'
                                    )

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
                        with ui.row().classes('w-full justify-between items-center'):
                            with ui.row().classes('items-center gap-2'):
                                ui.icon('psychology', size='sm', color='teal-4')
                                ui.label('Top Skills').classes('text-base font-bold text-slate-100')
                            ui.button(
                                'Edit skills',
                                icon='edit',
                                on_click=lambda: open_skills_editor(list(skills_list)),
                            ).props('flat dense').classes('text-xs text-teal-400')

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
                                    chip = ui.chip(
                                        tg.tag_name,
                                        color='indigo-9',
                                        removable=True,
                                    ).classes('text-xs text-indigo-200')

                                    def _on_tag_remove(e, tid=tag_id):
                                        # Removable chip sets value=False when the X is clicked
                                        if getattr(e, "value", False) is False:
                                            handle_remove_tag(tid)

                                    chip.on_value_change(_on_tag_remove)

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
                            result = dispatch_action(
                                "candidates.notes.add",
                                {"candidate_id": candidate.id, "content": note_in.value.strip()},
                                actor_type="ui",
                                session_id=f"candidate_{candidate.id}",
                            )
                            ui.notify('Note added.' if result.success else result.error, type='positive' if result.success else 'negative')
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
            sources = res.get('sources') or []
            if sources and sources[0].get('evidence'):
                ui.separator().classes('bg-indigo-900/30 my-2')
                ui.label('Evidence used').classes('text-[10px] font-semibold text-slate-400')
                for evidence in sources[0]['evidence'][:5]:
                    ui.label(evidence.get('label') or 'Profile evidence').classes('text-[10px] font-semibold text-amber-300')
                    ui.label(evidence.get('snippet') or '').classes('text-[11px] text-slate-400 leading-relaxed')

    def handle_remove_tag(tag_id: int):
        result = dispatch_action(
            "candidates.tags.remove",
            {"candidate_id": candidate_id, "tag_id": tag_id},
            actor_type="ui",
            session_id=f"candidate_{candidate_id}",
        )
        ui.notify('Tag removed.' if result.success else result.error, type='info' if result.success else 'negative')
        ui.navigate.to(f'/candidates/{candidate_id}')

    def open_read_page_dialog(url: str):
        """Open profile URL in Playwright, expand sections, show extracted text, optionally save."""
        import asyncio

        with ui.dialog() as dialog, ui.card().classes('w-full max-w-3xl p-5 th-card border border-teal-500/40 gap-3'):
            ui.label('Open & read profile page').classes('text-lg font-bold text-slate-100')
            ui.label(url).classes('text-[11px] text-teal-400 break-all')
            status_row = ui.row().classes('items-center gap-2')
            with status_row:
                ui.spinner(size='sm', color='teal')
                ui.label('Opening page, expanding sections, reading text…').classes('text-xs text-slate-400')
            result_box = ui.column().classes('w-full gap-2 max-h-[420px] overflow-y-auto')
            actions = ui.row().classes('w-full justify-end gap-2')

            async def run_read():
                from app.browser.page_reader import enrich_profile_from_url
                # Off the NiceGUI event loop so the WebSocket stays alive
                enriched = await asyncio.to_thread(
                    enrich_profile_from_url,
                    url,
                    headless=True,
                    candidate_id=candidate_id,
                    save_snapshot=True,
                )
                status_row.clear()
                result_box.clear()
                actions.clear()
                with status_row:
                    if enriched.get("status") == "success":
                        ui.icon('check_circle', color='teal-4', size='sm')
                        snap_note = " · snapshot saved" if enriched.get("snapshot") else ""
                        ui.label(
                            f'Read OK · expanded {enriched.get("expanded_clicks", 0)} section(s){snap_note}'
                        ).classes('text-xs text-teal-300')
                    elif enriched.get("blocked"):
                        ui.icon('lock', color='orange-4', size='sm')
                        ui.label('Login wall — connect the site under Settings → Connected sites, then retry.').classes(
                            'text-xs text-orange-300'
                        )
                    else:
                        ui.icon('error', color='red-4', size='sm')
                        ui.label(enriched.get("error") or "Read failed").classes('text-xs text-red-300')

                with result_box:
                    meta = []
                    if enriched.get("headline"):
                        meta.append(f"Headline: {enriched['headline']}")
                    if enriched.get("experience_years") is not None:
                        meta.append(f"Experience: {enriched['experience_years']} yrs")
                    if meta:
                        ui.label(" · ".join(meta)).classes('text-xs text-slate-300')
                    text = (enriched.get("text") or "").strip() or "(no text extracted)"
                    ui.markdown(f"```\n{text[:6000]}\n```").classes(
                        'text-[11px] text-slate-300 bg-slate-950/80 p-3 rounded border border-teal-900/30'
                    )

                with actions:
                    ui.button('Close', on_click=dialog.close).props('flat').classes('text-slate-400 text-xs')

                    def apply_to_profile():
                        years = enriched.get("experience_years")
                        summary = (enriched.get("summary") or enriched.get("text") or "")[:2000]
                        full = (enriched.get("text") or "").strip()
                        kwargs = {}
                        if years is not None:
                            kwargs["experience_years"] = years
                        if summary:
                            kwargs["summary"] = summary
                        if full:
                            kwargs["resume_text"] = full[:50000]
                        if not kwargs:
                            ui.notify('Nothing to apply.', type='warning')
                            return
                        update_candidate_via_action(**kwargs)
                        ui.notify('Profile updated from page snapshot text.', type='positive')
                        dialog.close()
                        ui.navigate.to(f'/candidates/{candidate_id}')

                    def extract_structured():
                        text = (enriched.get("text") or enriched.get("summary") or "").strip()
                        if not text:
                            ui.notify('No text to extract from.', type='warning')
                            return
                        dialog.close()
                        run_extract_then_review(
                            candidate_id,
                            text,
                            title='Review structured extract from page',
                        )

                    if enriched.get("status") == "success":
                        ui.button(
                            'Apply summary only', icon='save', on_click=apply_to_profile
                        ).props('flat dense').classes('text-xs text-slate-300')
                        ui.button(
                            'Extract structured profile', icon='auto_fix_fix', on_click=extract_structured
                        ).classes('th-primary-btn text-xs')

            ui.timer(0.05, run_read, once=True)
        dialog.open()

    def open_add_tag_dialog():
        with ui.dialog() as dialog, ui.card().classes('p-6 th-card border border-indigo-500/40 gap-3'):
            ui.label('Add Candidate Tag').classes('text-lg font-bold text-slate-100')
            tag_input = ui.input('Tag Name', placeholder='e.g., Top Tier, Remote Only').classes('w-full').props('dark outlined dense')
            with ui.row().classes('w-full justify-end gap-2 mt-2'):
                ui.button('Cancel', on_click=dialog.close).props('flat').classes('text-slate-400')
                def save_t():
                    if tag_input.value.strip():
                        result = dispatch_action(
                            "candidates.tags.add",
                            {"candidate_id": candidate_id, "tag_name": tag_input.value.strip()},
                            actor_type="ui",
                            session_id=f"candidate_{candidate_id}",
                        )
                        ui.notify('Tag added.' if result.success else result.error, type='positive' if result.success else 'negative')
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
                        result = dispatch_action(
                            "candidates.notes.add",
                            {
                                "candidate_id": candidate_id,
                                "content": note_content_in.value.strip(),
                                "author": author_in.value.strip() or "Recruiter",
                            },
                            actor_type="ui",
                            session_id=f"candidate_{candidate_id}",
                        )
                        ui.notify('Note saved.' if result.success else result.error, type='positive' if result.success else 'negative')
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
                        result = dispatch_action(
                            "candidates.experiences.save",
                            {
                                "candidate_id": candidate_id,
                                "company": comp_in.value.strip(),
                                "title": t_in.value.strip(),
                                "start_date": start_in.value.strip() or None,
                                "end_date": end_in.value.strip() or None,
                                "is_current": curr_chk.value,
                                "description": desc_in.value.strip() or None,
                            },
                            actor_type="ui",
                            session_id=f"candidate_{candidate_id}",
                        )
                        ui.notify('Experience added.' if result.success else result.error, type='positive' if result.success else 'negative')
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
                        result = dispatch_action(
                            "candidates.educations.save",
                            {
                                "candidate_id": candidate_id,
                                "institution": inst_in.value.strip(),
                                "degree": deg_in.value.strip() or None,
                                "field_of_study": field_in.value.strip() or None,
                                "start_year": int(s_yr.value) if s_yr.value else None,
                                "end_year": int(e_yr.value) if e_yr.value else None,
                            },
                            actor_type="ui",
                            session_id=f"candidate_{candidate_id}",
                        )
                        ui.notify('Education added.' if result.success else result.error, type='positive' if result.success else 'negative')
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
                    update_candidate_via_action(
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

    def open_skills_editor(current: list):
        skills_state = list(current or [])
        with ui.dialog() as dialog, ui.card().classes('w-full max-w-md p-5 th-card border border-teal-500/30 gap-3'):
            ui.label('Edit skills').classes('text-lg font-bold text-slate-100')
            chips_box = ui.row().classes('gap-1.5 flex-wrap min-h-[32px]')
            new_in = ui.input(placeholder='Add a skill and press Enter').classes('w-full text-xs').props('dark outlined dense')

            def refresh_chips():
                chips_box.clear()
                with chips_box:
                    for sk in skills_state:
                        chip = ui.chip(sk, color='teal-9', removable=True).classes('text-xs text-teal-100')

                        def _rm(e, name=sk):
                            if getattr(e, "value", False) is False and name in skills_state:
                                skills_state.remove(name)
                                refresh_chips()

                        chip.on_value_change(_rm)

            def add_skill():
                val = (new_in.value or "").strip()
                if not val:
                    return
                if val.lower() not in {s.lower() for s in skills_state}:
                    skills_state.append(val)
                new_in.value = ""
                refresh_chips()

            new_in.on('keydown.enter', add_skill)
            refresh_chips()

            with ui.row().classes('w-full justify-end gap-2 mt-2'):
                ui.button('Cancel', on_click=dialog.close).props('flat').classes('text-slate-400 text-xs')

                def save_skills():
                    update_candidate_via_action(skills=list(skills_state))
                    ui.notify('Skills updated.', type='positive')
                    dialog.close()
                    ui.navigate.to(f'/candidates/{candidate_id}')

                ui.button('Save', icon='check', on_click=save_skills).classes('th-teal-btn text-xs')
        dialog.open()

    def open_paste_extract_dialog():
        with ui.dialog() as dialog, ui.card().classes('w-full max-w-2xl p-5 th-card border border-teal-500/40 gap-3'):
            ui.label('Paste resume / profile text').classes('text-lg font-bold text-slate-100')
            ui.label('Paste LinkedIn text, resume body, or notes — we extract experience, education, and skills.').classes(
                'text-xs text-slate-400'
            )
            area = ui.textarea(placeholder='Paste text here…').classes('w-full min-h-[220px] text-xs').props('dark outlined')
            with ui.row().classes('w-full justify-end gap-2'):
                ui.button('Cancel', on_click=dialog.close).props('flat').classes('text-slate-400 text-xs')

                def go():
                    text = (area.value or "").strip()
                    if len(text) < 40:
                        ui.notify('Paste more profile text first.', type='warning')
                        return
                    dialog.close()
                    run_extract_then_review(candidate_id, text, title='Review paste extract')

                ui.button('Extract & review', icon='auto_fix_fix', on_click=go).classes('th-primary-btn text-xs')
        dialog.open()

    def open_resume_upload_dialog():
        with ui.dialog() as dialog, ui.card().classes(
            'w-full max-w-lg p-5 th-card border border-teal-500/40 gap-3'
        ):
            ui.label('Upload resume').classes('text-lg font-bold text-slate-100')
            ui.label('PDF, DOCX, or TXT · 8 MB maximum').classes('text-xs text-slate-400')
            status = ui.label('The file is read locally and retained only after profile review.').classes(
                'text-xs text-slate-500'
            )

            async def handle_upload(event):
                from app.candidates.resume_import import ResumeImportError, extract_resume_artifact

                try:
                    content = await event.file.read()
                    result = extract_resume_artifact(event.file.name, content)
                except ResumeImportError as exc:
                    status.set_text(str(exc))
                    ui.notify(str(exc), type='warning')
                    return
                except Exception as exc:
                    status.set_text('Resume import failed.')
                    ui.notify(f'Resume import failed: {exc}', type='negative')
                    return
                text = str(result['text'])
                dialog.close()
                run_extract_then_review(
                    candidate_id,
                    text,
                    title=f'Review {result["filename"]}',
                )

            ui.upload(
                on_upload=handle_upload,
                auto_upload=True,
                max_file_size=8 * 1024 * 1024,
                max_files=1,
            ).props('accept=.pdf,.docx,.txt flat bordered').classes('w-full')
            with ui.row().classes('w-full justify-end'):
                ui.button('Cancel', on_click=dialog.close).props('flat').classes('text-slate-400 text-xs')
        dialog.open()

    def open_fill_from_page_dialog():
        with SessionFactory() as db:
            cand = get_candidate(db, candidate_id)
            default_url = (cand.linkedin_url or cand.portfolio_url or cand.github_url or "") if cand else ""
        with ui.dialog() as dialog, ui.card().classes('w-full max-w-lg p-5 th-card border border-teal-500/40 gap-3'):
            ui.label('Fill from LinkedIn / page').classes('text-lg font-bold text-slate-100')
            url_in = ui.input('Profile URL', value=default_url).classes('w-full').props('dark outlined dense')
            status_lbl = ui.label('').classes('text-xs text-slate-400')

            async def run_fill():
                import asyncio
                url = (url_in.value or "").strip()
                if not url:
                    ui.notify('Enter a profile URL.', type='warning')
                    return
                status_lbl.set_text('Reading page & saving snapshot…')
                from app.browser.page_reader import enrich_profile_from_url
                enriched = await asyncio.to_thread(
                    enrich_profile_from_url,
                    url,
                    headless=True,
                    candidate_id=candidate_id,
                    save_snapshot=True,
                )
                text = (enriched.get("text") or "").strip()
                if enriched.get("status") != "success" or len(text) < 40:
                    status_lbl.set_text(enriched.get("error") or "Could not read enough text.")
                    ui.notify('Page read failed or empty.', type='warning')
                    return
                update_candidate_via_action(resume_text=text[:50000])
                dialog.close()
                run_extract_then_review(
                    candidate_id,
                    text,
                    title='Review extract from page',
                    draft_overrides={
                        'profile_image_url': enriched.get('profile_image_url'),
                        'location': enriched.get('location'),
                    },
                )

            with ui.row().classes('w-full justify-end gap-2'):
                ui.button('Cancel', on_click=dialog.close).props('flat').classes('text-slate-400 text-xs')
                ui.button('Read & extract', icon='travel_explore', on_click=run_fill).classes('th-primary-btn text-xs')
        dialog.open()

    def open_send_intake_dialog():
        from app.hunts.service import list_hunts

        with SessionFactory() as db:
            cand = get_candidate(db, candidate_id)
            hunts = list_hunts(db) or []
            hunt_options = {0: 'No hunt (general form)'}
            for h in hunts:
                hunt_options[h.id] = f"#{h.id} {h.title}" + (f" — {h.target_role}" if h.target_role else "")

        with ui.dialog() as dialog, ui.card().classes('w-full max-w-xl p-5 th-card border border-amber-500/40 gap-3'):
            ui.label('Send profile form').classes('text-lg font-bold text-slate-100')
            ui.label(
                'Creates a magic link the candidate can open. For external candidates, expose this app via a tunnel.'
            ).classes('text-xs text-slate-400')
            hunt_sel = ui.select(hunt_options, value=0, label='Link to hunt JD').classes('w-full').props('dark outlined dense')
            url_box = ui.input('Form URL').classes('w-full').props('dark outlined dense readonly')
            msg_box = ui.textarea('Draft outreach (copy into email / LinkedIn)').classes('w-full min-h-[140px]').props('dark outlined')

            def generate():
                hid = hunt_sel.value
                hunt_id = int(hid) if hid and int(hid) != 0 else None
                with SessionFactory() as db:
                    req = create_intake_request(db, candidate_id, hunt_id=hunt_id, mark_sent=True)
                    if not req:
                        ui.notify('Could not create form link.', type='negative')
                        return
                    url = intake_url_for_token(req.token)
                    jd = get_hunt_jd_context(db, hunt_id)
                    cand = get_candidate(db, candidate_id)
                    msg = draft_outreach_message(
                        cand,
                        url=url,
                        hunt_title=jd.get("title"),
                        role=jd.get("role"),
                    )
                url_box.value = url
                msg_box.value = msg
                ui.notify('Form link ready — copy and send.', type='positive')

            with ui.row().classes('w-full justify-between gap-2'):
                ui.button('Generate link', icon='link', on_click=generate).classes('th-primary-btn text-xs')
                ui.button('Close', on_click=dialog.close).props('flat').classes('text-slate-400 text-xs')
        dialog.open()

    def open_intake_review(submission_id: int, payload: dict):
        draft = {
            "experiences": payload.get("experiences") or [],
            "educations": payload.get("educations") or [],
            "skills": payload.get("skills") or [],
            "summary": payload.get("summary"),
            "experience_years": payload.get("experience_years"),
            "headline": None,
        }

        # Use shared review for payload sections, then mark submission accepted on apply
        with ui.dialog() as dialog, ui.card().classes('w-full max-w-3xl p-5 th-card border border-orange-500/40 gap-3'):
            ui.label('Review candidate form submission').classes('text-lg font-bold text-slate-100')
            fit = payload.get("jd_fit") or {}
            if fit:
                with ui.column().classes('w-full gap-1 p-3 bg-slate-950/60 rounded border border-orange-900/40'):
                    ui.label('JD fit answers').classes('text-xs font-semibold text-orange-200')
                    for k, label in (
                        ("availability", "Availability"),
                        ("notice_period", "Notice period"),
                        ("salary_expectation", "Salary expectation"),
                        ("why_fit", "Why fit"),
                    ):
                        if fit.get(k):
                            ui.label(f"{label}: {fit.get(k)}").classes('text-xs text-slate-300')

            with ui.row().classes('w-full justify-end gap-2'):
                def reject():
                    with SessionFactory() as db:
                        apply_intake_submission(db, submission_id, accept=False)
                    ui.notify('Submission rejected.', type='info')
                    dialog.close()
                    ui.navigate.to(f'/candidates/{candidate_id}')

                def accept_and_edit():
                    dialog.close()

                    def on_applied():
                        with SessionFactory() as db:
                            # Mark accepted without re-applying sections (already written by review)
                            from app.candidates.models import CandidateIntakeSubmission, CandidateIntakeRequest
                            from datetime import datetime, timezone
                            sub = db.get(CandidateIntakeSubmission, submission_id)
                            if sub and sub.review_status == "pending":
                                sub.review_status = "accepted"
                                sub.reviewed_at = datetime.now(timezone.utc)
                                req = db.get(CandidateIntakeRequest, sub.request_id)
                                if req:
                                    req.status = "accepted"
                                # Still write JD fit note if present
                                fit = payload.get("jd_fit") or {}
                                fit_lines = []
                                for key, label in (
                                    ("availability", "Availability"),
                                    ("notice_period", "Notice period"),
                                    ("salary_expectation", "Salary expectation"),
                                    ("why_fit", "Why fit"),
                                ):
                                    val = fit.get(key)
                                    if val:
                                        fit_lines.append(f"{label}: {val}")
                                if fit_lines:
                                    from app.candidates.models import CandidateNote
                                    db.add(CandidateNote(
                                        candidate_id=candidate_id,
                                        content="Candidate intake form — JD fit:\n" + "\n".join(fit_lines),
                                        author="Intake Form",
                                    ))
                                db.commit()
                        ui.navigate.to(f'/candidates/{candidate_id}')

                    open_profile_sections_review(
                        candidate_id,
                        draft,
                        title='Apply form answers to profile',
                        on_applied=on_applied,
                    )

                ui.button('Reject', on_click=reject).props('flat').classes('text-red-300 text-xs')
                ui.button('Review & apply', icon='check', on_click=accept_and_edit).classes('th-primary-btn text-xs')
        dialog.open()


def candidate_detail_page(candidate_id: int):
    create_layout(lambda: render_candidate_detail(candidate_id))
