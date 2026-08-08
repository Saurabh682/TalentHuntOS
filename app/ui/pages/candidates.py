"""NiceGUI Candidate Database & CRM Management Page with Vector Search & LlamaIndex RAG."""

import json
from nicegui import ui
from app.ui.layout import create_layout
from app.infrastructure.db import SessionFactory, init_db
from app.candidates.service import (
    seed_demo_candidates_if_empty,
    list_candidates,
    create_candidate,
    delete_candidate,
)
from app.candidates.search import candidate_search_index
from app.candidates.rag import candidate_rag


def render_candidates():
    """Render the main Candidate Database page content."""
    init_db()
    with SessionFactory() as db:
        seed_demo_candidates_if_empty(db)

    selected_status = {"value": "All"}
    search_mode = {"mode": "keyword"}  # "keyword" or "vector"
    refresh_view_ref = {"fn": lambda: None}

    def open_rag_qa_dialog():
        with ui.dialog() as dialog, ui.card().classes('w-full max-w-2xl p-6 th-card border border-indigo-500/40 gap-4'):
            ui.label('LlamaIndex RAG Candidate Q&A').classes('th-display text-slate-100')
            ui.label('Ask natural language questions across all stored candidate profiles & resumes.').classes('th-caption text-slate-400')

            qa_input = ui.input(placeholder='e.g., Who has experience with Docker and Kubernetes?').classes('w-full').props('dark outlined dense')
            answer_box = ui.markdown('').classes('w-full p-4 bg-slate-900/60 rounded-lg border border-indigo-900/30 text-sm text-slate-200 hidden')

            with ui.row().classes('w-full justify-end gap-3 mt-2'):
                ui.button('Close', on_click=dialog.close).props('flat').classes('text-slate-400')
                def run_query():
                    q = qa_input.value.strip()
                    if not q:
                        return
                    with SessionFactory() as db:
                        res = candidate_rag.query(db, q)
                    answer_box.content = res
                    answer_box.classes(remove='hidden')

                ui.button('Ask RAG Engine', icon='psychology', on_click=run_query).classes('bg-indigo-600 text-white text-xs px-4 py-2 rounded')
        dialog.open()

    def confirm_delete_candidate(cid: int, name: str):
        with ui.dialog() as dialog, ui.card().classes('p-6 th-card border border-red-500/30 gap-4'):
            ui.label(f'Delete Candidate "{name}"?').classes('text-lg font-bold text-slate-100')
            ui.label('This will permanently delete candidate profile, experiences, notes, and vector search indices.').classes('text-xs text-slate-400')
            with ui.row().classes('w-full justify-end gap-2'):
                ui.button('Cancel', on_click=dialog.close).props('flat').classes('text-slate-400')
                def do_del():
                    try:
                        with SessionFactory() as db:
                            delete_candidate(db, cid)
                        ui.notify(f'Candidate "{name}" deleted.', type='info')
                        dialog.close()
                        refresh_view_ref["fn"]()
                    except Exception as e:
                        ui.notify(f"Error: {e}", type="negative")
                ui.button('Delete', color='red', on_click=do_del).classes('bg-red-600 text-white text-xs px-4 py-2 rounded')
        dialog.open()

    def open_create_candidate_dialog():
        with ui.dialog() as dialog, ui.card().classes('w-full max-w-xl p-6 th-card border border-teal-500/30 gap-4'):
            ui.label('Create Candidate Profile').classes('th-display text-slate-100')
            ui.label('Add candidate details to global database and automatically index into ChromaDB.').classes('th-caption text-slate-400')

            with ui.column().classes('w-full gap-1'):
                ui.label('Full Name').classes('th-caption text-slate-300')
                name_in = ui.input(placeholder='e.g., Alex Mercer').classes('w-full').props('dark outlined dense')

            with ui.column().classes('w-full gap-1'):
                ui.label('Current Title').classes('th-caption text-slate-300')
                title_in = ui.input(placeholder='e.g., Senior Systems Architect').classes('w-full').props('dark outlined dense')

            with ui.column().classes('w-full gap-1'):
                ui.label('Current Company').classes('th-caption text-slate-300')
                company_in = ui.input(placeholder='e.g., Cyberdyne Systems').classes('w-full').props('dark outlined dense')

            with ui.column().classes('w-full gap-1'):
                ui.label('Email Address').classes('th-caption text-slate-300')
                email_in = ui.input(placeholder='e.g., alex.m@example.com').classes('w-full').props('dark outlined dense')

            with ui.column().classes('w-full gap-1'):
                ui.label('Location').classes('th-caption text-slate-300')
                loc_in = ui.input(placeholder='e.g., San Francisco, CA').classes('w-full').props('dark outlined dense')

            with ui.column().classes('w-full gap-1'):
                ui.label('Experience Years').classes('th-caption text-slate-300')
                exp_in = ui.number(value=5.0, step=0.5).classes('w-full').props('dark outlined dense')

            with ui.column().classes('w-full gap-1'):
                ui.label('Skills (comma-separated)').classes('th-caption text-slate-300')
                skills_in = ui.input(placeholder='e.g., Python, C++, CUDA, PyTorch').classes('w-full').props('dark outlined dense')

            with ui.column().classes('w-full gap-1'):
                ui.label('Profile Summary / Bio').classes('th-caption text-slate-300')
                summary_in = ui.textarea(placeholder='Key accomplishments...').classes('w-full').props('dark outlined dense')

            with ui.row().classes('w-full justify-end gap-3 mt-4'):
                ui.button('Cancel', on_click=dialog.close).props('flat').classes('text-slate-400')
                def save():
                    if not name_in.value.strip():
                        ui.notify('Candidate full name is required.', type='negative')
                        return
                    skills_list = [s.strip() for s in skills_in.value.split(',') if s.strip()] if skills_in.value else []
                    try:
                        with SessionFactory() as db:
                            create_candidate(
                                db,
                                full_name=name_in.value.strip(),
                                current_title=title_in.value.strip() or None,
                                current_company=company_in.value.strip() or None,
                                email=email_in.value.strip() or None,
                                location=loc_in.value.strip() or None,
                                experience_years=float(exp_in.value) if exp_in.value else 0.0,
                                skills=skills_list,
                                summary=summary_in.value.strip() or None,
                            )
                        ui.notify('Candidate created and indexed successfully!', type='positive')
                        dialog.close()
                        refresh_view_ref["fn"]()
                    except Exception as e:
                        ui.notify(f"Error: {e}", type="negative")

                ui.button('Save Candidate', icon='save', on_click=save).classes('th-teal-btn')
        dialog.open()

    with ui.column().classes('w-full gap-6'):
        # Page Title Header
        with ui.row().classes('w-full justify-between items-center'):
            with ui.column().classes('gap-1'):
                ui.label('Candidate Database & CRM').classes('text-2xl font-bold text-slate-100')
                ui.label('Global talent database with ChromaDB FastEmbed vector search & LlamaIndex RAG Q&A.').classes('text-sm text-slate-400')

            with ui.row().classes('items-center gap-3'):
                ui.button(
                    'LlamaIndex Q&A', icon='psychology', color='indigo',
                    on_click=open_rag_qa_dialog
                ).classes('bg-indigo-600 hover:bg-indigo-500 text-white font-medium px-4 py-2 rounded-lg text-sm')

                ui.button(
                    'Add Candidate', icon='person_add', color='teal',
                    on_click=open_create_candidate_dialog
                ).classes('th-teal-btn')

        # Filter & Dual Search Control Card
        with ui.card().classes('w-full p-4 th-card border border-teal-900/30 gap-4'):
            with ui.row().classes('w-full justify-between items-center flex-wrap gap-4'):
                # Left side: Mode toggle & Status filters
                with ui.row().classes('items-center gap-3 flex-wrap'):
                    ui.label('Search Mode:').classes('text-xs font-semibold text-teal-400')
                    mode_toggle = ui.toggle(
                        options={'keyword': 'Keyword Filter', 'vector': 'Vector Similarity (FastEmbed)'},
                        value='keyword',
                        on_change=lambda e: set_search_mode(e.value)
                    ).props('dense dark').classes('text-xs')

                    ui.separator().props('vertical').classes('h-6 bg-teal-900/40')

                    ui.label('Status:').classes('text-xs text-slate-400')
                    for st in ["All", "Active", "Passive", "Placed", "Archived"]:
                        ui.button(
                            st, on_click=lambda e, s=st: set_status_filter(s)
                        ).props('dense flat').classes('text-xs px-2.5 py-1 rounded-full bg-slate-800 text-slate-300 hover:text-teal-400')

                # Right side: Search Input Box
                search_input = ui.input(
                    placeholder='Search candidates by keyword...'
                ).classes('grow max-w-md text-sm').props('dense dark outlined rounded')

        # Semantic Search Banner / Info when vector mode is selected
        search_banner = ui.element('div').classes('w-full')

        # Candidates Grid Container
        candidates_container = ui.column().classes('w-full gap-4')

        def set_search_mode(mode: str):
            search_mode["mode"] = mode
            search_input.placeholder = (
                'Enter semantic search prompt (e.g. "Senior PyTorch engineer with local model experience")...'
                if mode == 'vector'
                else 'Search candidates by name, title, skill, or location...'
            )
            refresh_view()

        def set_status_filter(status: str):
            selected_status["value"] = status
            refresh_view()

        def refresh_view():
            candidates_container.clear()
            search_banner.clear()

            kw_text = search_input.value.strip() if search_input.value else ""

            with SessionFactory() as db:
                if search_mode["mode"] == "vector" and kw_text:
                    # Perform ChromaDB FastEmbed vector search
                    hits = candidate_search_index.search_candidates(query=kw_text, top_k=20)
                    hit_map = {h["candidate_id"]: h for h in hits}

                    all_cands = list_candidates(db)

                    display_cands = []
                    for c in all_cands:
                        if c.id in hit_map:
                            score = hit_map[c.id]["similarity_score"]
                            display_cands.append((c, score))

                    display_cands.sort(key=lambda x: x[1], reverse=True)

                    with search_banner:
                        with ui.card().classes('w-full p-3 bg-teal-950/40 border border-teal-500/30 rounded-lg flex-row justify-between items-center mb-2'):
                            with ui.row().classes('items-center gap-2'):
                                ui.icon('hub', color='teal-4', size='sm')
                                ui.label(f'Vector Similarity Search Results for: "{kw_text}"').classes('text-xs text-teal-300 font-medium')
                            ui.badge(f'{len(display_cands)} matched profiles', color='teal').classes('text-xs')

                else:
                    cands = list_candidates(
                        db,
                        search=kw_text if search_mode["mode"] == "keyword" else None,
                        status=selected_status["value"],
                    )
                    display_cands = [(c, None) for c in cands]

                with candidates_container:
                    if not display_cands:
                        with ui.card().classes('w-full p-12 th-card items-center justify-center text-center gap-4'):
                            ui.icon('person_search', size='48px', color='slate-500')
                            ui.label('No Candidates Found').classes('th-subheading text-slate-100')
                            ui.label('No candidate profiles match your query or selected status filters.').classes('th-body text-slate-400 max-w-md')
                            ui.button(
                                'Add First Candidate', icon='person_add',
                                on_click=open_create_candidate_dialog
                            ).classes('th-teal-btn mt-2')
                        return

                    # Render Candidate Cards / Table rows
                    for cand, match_score in display_cands:
                        cand_id = cand.id
                        skills = []
                        if cand.profile and cand.profile.skills_json:
                            try:
                                skills = json.loads(cand.profile.skills_json)
                            except Exception:
                                skills = []

                        with ui.card().classes('w-full p-5 th-card border border-teal-900/30 hover:border-teal-500/40 transition-all duration-150 gap-3'):
                            with ui.row().classes('w-full justify-between items-start flex-wrap gap-2'):
                                # Candidate Main Info
                                with ui.row().classes('items-center gap-4'):
                                    ui.avatar(cand.full_name[0].upper() if cand.full_name else '?', color='teal-9', text_color='teal-2').classes('font-bold text-lg')
                                    with ui.column().classes('gap-0'):
                                        with ui.row().classes('items-center gap-2'):
                                            ui.link(
                                                cand.full_name,
                                                target=f'/candidates/{cand_id}'
                                            ).classes('text-lg font-bold text-slate-100 hover:text-teal-400 transition-colors')
                                            st_color = 'teal' if cand.status == 'Active' else ('amber' if cand.status == 'Passive' else 'blue-grey')
                                            ui.badge(cand.status, color=st_color).classes('text-[10px] px-2 py-0.5')

                                        subtitle = f"{cand.current_title or 'Candidate'} • {cand.current_company or 'N/A'}"
                                        ui.label(subtitle).classes('text-xs text-slate-400 font-medium')

                                # Right side: Match score & Actions
                                with ui.row().classes('items-center gap-3'):
                                    if match_score is not None:
                                        sc_color = 'teal' if match_score >= 85 else ('amber' if match_score >= 70 else 'indigo')
                                        with ui.column().classes('items-end gap-0'):
                                            ui.badge(f"{match_score:.1f}% Match", color=sc_color).classes('text-xs font-bold px-2 py-1')
                                            ui.label('FastEmbed Score').classes('text-[10px] text-slate-400')

                                    ui.button(
                                        '360° Profile', icon='visibility', color='teal',
                                        on_click=lambda e, cid=cand_id: ui.navigate.to(f'/candidates/{cid}')
                                    ).classes('th-teal-btn text-xs')

                                    ui.button(
                                        icon='delete_outline',
                                        on_click=lambda e, cid=cand_id, name=cand.full_name: confirm_delete_candidate(cid, name)
                                    ).props('flat round dense').classes('text-slate-500 hover:text-red-400').tooltip('Delete Candidate')

                            # Location & Experience metadata row
                            with ui.row().classes('items-center gap-4 text-xs text-slate-400 px-1'):
                                if cand.location:
                                    with ui.row().classes('items-center gap-1'):
                                        ui.icon('place', size='xs', color='amber-4')
                                        ui.label(cand.location)
                                if cand.experience_years:
                                    with ui.row().classes('items-center gap-1'):
                                        ui.icon('work_history', size='xs', color='teal-4')
                                        ui.label(f"{cand.experience_years} yrs exp")
                                if cand.email:
                                    with ui.row().classes('items-center gap-1'):
                                        ui.icon('email', size='xs', color='indigo-4')
                                        ui.label(cand.email)

                            # Headline / Summary snippet
                            if cand.profile and (cand.profile.headline or cand.profile.summary):
                                text_snippet = cand.profile.headline or cand.profile.summary
                                ui.label(text_snippet).classes('text-xs text-slate-300 line-clamp-2 px-1')

                            # Skills & Tags Row
                            with ui.row().classes('w-full justify-between items-center pt-1 border-t border-teal-900/20 flex-wrap gap-2'):
                                with ui.row().classes('items-center gap-1.5 flex-wrap'):
                                    for sk in skills[:7]:
                                        ui.badge(sk, color='slate-800').classes('text-[11px] text-teal-300 px-2 py-0.5 border border-teal-900/40 rounded-md')
                                    if len(skills) > 7:
                                        ui.label(f"+{len(skills) - 7} more").classes('text-[10px] text-slate-500')

                                with ui.row().classes('items-center gap-1.5'):
                                    for tg in cand.tags:
                                        ui.badge(tg.tag_name, color='indigo-9').classes('text-[10px] text-indigo-200 px-2 py-0.5')

        refresh_view_ref["fn"] = refresh_view
        search_input.on('update:model-value', lambda e: refresh_view())
        refresh_view()

    def open_rag_qa_dialog():
        with ui.dialog() as dialog, ui.card().classes('w-full max-w-2xl p-6 th-card border border-indigo-500/40 gap-4'):
            with ui.row().classes('items-center gap-3'):
                ui.icon('psychology', size='md', color='indigo-4')
                with ui.column().classes('gap-0'):
                    ui.label('LlamaIndex Candidate RAG Q&A').classes('text-xl font-bold text-slate-100')
                    ui.label('Ask complex queries across the entire Candidate database.').classes('text-xs text-slate-400')

            qa_input = ui.input(
                placeholder='e.g., "Who has the best experience in vector search and local models?"'
            ).classes('w-full').props('dark outlined dense')

            output_area = ui.column().classes('w-full gap-3 p-4 bg-slate-950/80 border border-teal-900/30 rounded-lg min-h-[150px]')
            with output_area:
                ui.label('Enter your query above to run LlamaIndex vector retrieval & answer synthesis.').classes('text-xs text-slate-500 italic')

            def run_rag_query():
                q_text = qa_input.value.strip()
                if not q_text:
                    ui.notify('Please enter a question.', type='warning')
                    return

                output_area.clear()
                with output_area:
                    with ui.row().classes('items-center gap-2 text-teal-400 text-xs'):
                        ui.spinner(size='sm', color='teal')
                        ui.label('LlamaIndex searching and synthesizing answer...')

                with SessionFactory() as db:
                    result = candidate_rag.query_candidate_database(query=q_text, db=db)

                output_area.clear()
                with output_area:
                    ui.label('AI Answer:').classes('text-xs font-bold text-teal-400')
                    ui.markdown(result["answer"]).classes('text-sm text-slate-200 leading-relaxed')

                    if result.get("sources"):
                        ui.separator().classes('bg-teal-900/30 my-2')
                        ui.label('Relevant Candidate Sources:').classes('text-[11px] font-semibold text-slate-400')
                        with ui.row().classes('gap-2 flex-wrap'):
                            for src in result["sources"]:
                                score_str = f" ({src.get('relevance_score')}%)" if src.get("relevance_score") else ""
                                ui.chip(f"#{src['id']} {src['full_name']}{score_str}", color='teal-9').classes('text-[10px]')

            with ui.row().classes('w-full justify-between items-center pt-2'):
                ui.button('Close', on_click=dialog.close).props('flat').classes('text-slate-400 text-xs')
                ui.button('Ask LlamaIndex', icon='send', color='indigo', on_click=run_rag_query).classes('bg-indigo-600 hover:bg-indigo-500 text-white text-xs px-4 py-2 rounded')

        dialog.open()


def candidates_page():
    create_layout(render_candidates)
