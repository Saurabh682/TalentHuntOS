"""NiceGUI Candidate Database & CRM Management Page with Vector Search & LlamaIndex RAG."""

import json
from nicegui import ui
from app.actions.api import approve_and_dispatch, cancel_approval, dispatch_action, dispatch_preview
from app.ui.layout import create_layout
from app.infrastructure.db import SessionFactory, init_db
from app.candidates.service import (
    seed_demo_candidates_if_empty,
    list_candidates,
    update_candidate,
)
from app.candidates.search import candidate_search_index
from app.candidates.rag import candidate_rag
from app.hunts.web_sourcing import get_hunt_labels_for_candidates
from app.hunts.playbook import ROGUE_TAG
from app.hunts.service import list_hunts
from app.candidates.models import Candidate


def _tag_target(label: str, candidate, hunt_ids_by_title: dict[str, int]) -> tuple[str, str] | None:
    """Resolve navigational tags to a URL and tooltip."""
    normalized = (label or "").strip().lower()
    hunt_title = normalized[6:].strip() if normalized.startswith("hunt: ") else normalized
    if hunt_title in hunt_ids_by_title:
        return (f"/hunts/{hunt_ids_by_title[hunt_title]}/pipeline", "Open hunt pipeline")
    if normalized in {"linkedin", "linkedin profile"} and candidate.linkedin_url:
        return (candidate.linkedin_url, "Open LinkedIn profile")
    if normalized in {"github", "github profile"} and candidate.github_url:
        return (candidate.github_url, "Open GitHub profile")
    if normalized in {"naukri", "portfolio", "website", "profile"} and candidate.portfolio_url:
        return (candidate.portfolio_url, "Open external profile")
    return None


def _render_tag(label: str, color: str, target: tuple[str, str] | None, classes: str) -> None:
    if target:
        url, tooltip = target
        background = {"teal-9": "#004d40", "indigo-9": "#283593"}.get(color, "#263238")
        ui.link(label, target=url, new_tab=True).classes(
            f"{classes} cursor-pointer hover:brightness-125 transition-all"
        ).style(f"background:{background};border-radius:4px;text-decoration:none").tooltip(tooltip)
    else:
        ui.badge(label, color=color).classes(classes)


def render_candidates():
    """Render the main Candidate Database page content."""
    init_db()
    with SessionFactory() as db:
        seed_demo_candidates_if_empty(db)

    selected_status = {"value": "All"}
    selected_candidate_id = {"value": None}
    search_mode = {"mode": "keyword"}  # "keyword" or "vector"
    refresh_view_ref = {"fn": lambda: None}

    def _author() -> str:
        try:
            return (ui.app.storage.user.get("playbook_author") or "Recruiter").strip() or "Recruiter"
        except Exception:
            return "Recruiter"

    def open_rogue_dialog(cand_id: int, cand_name: str, is_rogue: bool):
        if is_rogue:
            result = dispatch_action(
                "candidates.rogue.set",
                {"candidate_id": cand_id, "enabled": False, "author": _author()},
                actor_type="ui",
                session_id=f"candidate_{cand_id}",
            )
            ui.notify(
                f'Cleared Rogue tag on {cand_name}' if result.success else result.error,
                type='info' if result.success else 'negative',
            )
            refresh_view_ref["fn"]()
            return

        with ui.dialog() as dialog, ui.card().classes('w-full max-w-md p-5 th-card border border-orange-500/40 gap-3'):
            ui.label('Mark as Rogue profile').classes('text-lg font-bold text-slate-100')
            ui.label(cand_name).classes('text-sm text-orange-300')
            ui.label(
                'Use this for bad-fit / wrong-role leads so the team skips them next time. Logged to the shared Playbook.'
            ).classes('text-xs text-slate-400')
            note_in = ui.textarea(
                placeholder='Optional — why this profile is rogue (wrong role, spam, irrelevant…)'
            ).classes('w-full').props('dark outlined dense')
            with ui.row().classes('w-full justify-end gap-2 mt-1'):
                ui.button('Cancel', on_click=dialog.close).props('flat').classes('text-slate-400 text-xs')

                def confirm():
                    note = (note_in.value or "").strip() or None
                    result = dispatch_action(
                        "candidates.rogue.set",
                        {
                            "candidate_id": cand_id,
                            "enabled": True,
                            "note": note,
                            "author": _author(),
                        },
                        actor_type="ui",
                        session_id=f"candidate_{cand_id}",
                    )
                    if not result.success:
                        ui.notify(result.error or "Failed", type="negative")
                        return
                    ui.notify(f'Marked {cand_name} as Rogue — logged to Playbook', type='warning')
                    dialog.close()
                    refresh_view_ref["fn"]()

                ui.button('Mark Rogue', icon='report', on_click=confirm).props('color=orange').classes('text-xs')
        dialog.open()

    def open_assign_hunt_dialog(cand_id: int, cand_name: str, current_hunts: list):
        """Assign (or move) this candidate to another Talent Hunt profile."""
        with SessionFactory() as db:
            hunts = list_hunts(db, status="Active") or list_hunts(db)
            options = {str(h.id): f"{h.title} ({h.target_role or 'role n/a'})" for h in hunts}
            cand = db.get(Candidate, cand_id)

        if not options:
            ui.notify('No Talent Hunts found. Create one on the Hunts page first.', type='warning')
            return

        with ui.dialog() as dialog, ui.card().classes(
            'w-full max-w-md p-5 th-card border border-teal-500/40 gap-3'
        ):
            ui.label('Assign to Talent Hunt').classes('text-lg font-bold text-slate-100')
            ui.label(cand_name).classes('text-sm text-teal-300')
            if current_hunts:
                ui.label('Currently on: ' + ', '.join(current_hunts)).classes('text-[11px] text-slate-400')
            else:
                ui.label('Not linked to any hunt yet.').classes('text-[11px] text-slate-500')

            hunt_select = ui.select(
                options=options,
                label='Talent Hunt',
                value=next(iter(options.keys())),
            ).classes('w-full').props('dark outlined dense')

            move_only = ui.checkbox(
                'Remove from other hunts (move instead of add)',
                value=False,
            ).classes('text-xs text-slate-300')

            note_in = ui.input(
                placeholder='Optional note (e.g. better fit for this role)'
            ).classes('w-full').props('dark outlined dense')

            with ui.row().classes('w-full justify-end gap-2 mt-1'):
                ui.button('Cancel', on_click=dialog.close).props('flat').classes('text-slate-400 text-xs')

                def confirm_assign():
                    hid = int(hunt_select.value)
                    result = dispatch_action(
                        'pipeline.enroll',
                        {
                            'candidate_id': cand_id,
                            'hunt_id': hid,
                            'move_from_other_hunts': bool(move_only.value),
                            'note': (note_in.value or '').strip() or None,
                        },
                        actor_type='ui',
                        session_id=f'candidate_{cand_id}',
                    )
                    if not result.success:
                        ui.notify(result.error or 'Candidate assignment failed.', type='negative')
                        return

                    ui.notify(
                        f'{"Moved" if move_only.value else "Added"} {cand_name} → {options[str(hid)]}. Undo is available.',
                        type='positive',
                    )
                    dialog.close()
                    refresh_view_ref["fn"]()

                ui.button(
                    'Assign', icon='campaign', on_click=confirm_assign
                ).classes('th-teal-btn text-xs')
        dialog.open()

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

    def open_duplicate_review():
        result = dispatch_action(
            "candidates.duplicates.list",
            {"limit": 100},
            actor_type="ui",
            session_id="candidate_duplicates",
        )
        if not result.success:
            ui.notify(result.error or "Duplicate scan failed.", type="negative")
            return
        pairs = (result.data or {}).get("duplicates") or []
        if not pairs:
            ui.notify("No likely duplicate Candidates found.", type="positive")
            return

        with ui.dialog() as dialog, ui.card().classes(
            'w-full max-w-4xl max-h-[82vh] p-0 th-card border border-teal-500/30 gap-0 overflow-hidden'
        ):
            with ui.row().classes('w-full items-center justify-between px-5 py-4 border-b border-slate-700/70'):
                with ui.column().classes('gap-0'):
                    ui.label('Duplicate Candidates').classes('text-lg font-bold text-slate-100')
                    ui.label(f'{len(pairs)} likely pair(s) need identity review.').classes('text-xs text-slate-400')
                ui.button(icon='close', on_click=dialog.close).props('flat round dense').tooltip('Close')

            with ui.column().classes('w-full gap-0 overflow-y-auto'):
                for pair in pairs:
                    left = pair["left"]
                    right = pair["right"]
                    with ui.element('section').classes('w-full px-5 py-4 border-b border-slate-800'):
                        with ui.row().classes('w-full items-start gap-4 flex-nowrap'):
                            with ui.column().classes('min-w-0 flex-1 gap-1'):
                                ui.label(left["full_name"]).classes('font-semibold text-slate-100')
                                ui.label(
                                    f'#{left["id"]} · {left.get("current_title") or "Title unavailable"} · '
                                    f'{left.get("current_company") or "Company unavailable"}'
                                ).classes('text-xs text-slate-400')
                            ui.icon('compare_arrows').classes('text-teal-400 mt-1')
                            with ui.column().classes('min-w-0 flex-1 gap-1'):
                                ui.label(right["full_name"]).classes('font-semibold text-slate-100')
                                ui.label(
                                    f'#{right["id"]} · {right.get("current_title") or "Title unavailable"} · '
                                    f'{right.get("current_company") or "Company unavailable"}'
                                ).classes('text-xs text-slate-400')
                        ui.label(' · '.join(pair.get("reasons") or [])).classes('text-xs text-teal-300 mt-2')
                        with ui.row().classes('w-full justify-end gap-2 mt-3'):
                            ui.button(
                                f'Keep #{left["id"]}', icon='merge',
                                on_click=lambda l=left, r=right: open_merge_preview(l, r, dialog),
                            ).props('outline dense no-caps').classes('text-xs')
                            ui.button(
                                f'Keep #{right["id"]}', icon='merge',
                                on_click=lambda l=right, r=left: open_merge_preview(l, r, dialog),
                            ).props('outline dense no-caps').classes('text-xs')
        dialog.open()

    def open_merge_preview(survivor: dict, source: dict, review_dialog):
        approval_session = f'candidate_merge_{survivor["id"]}_{source["id"]}'
        requested = dispatch_preview(
            "candidates.merge",
            {"survivor_id": survivor["id"], "source_id": source["id"]},
            actor_type="ui",
            session_id=approval_session,
        )
        if not requested.success:
            ui.notify(requested.error or "Could not create merge preview.", type="negative")
            return
        pending = requested.data or {}
        preview = pending.get("preview") or {}
        refs = preview.get("source_references") or {}

        with ui.dialog() as confirm_dialog, ui.card().classes(
            'w-full max-w-xl p-5 th-card border border-orange-500/40 gap-3'
        ):
            ui.label('Merge duplicate Candidates?').classes('text-lg font-bold text-slate-100')
            ui.label(preview.get("summary") or "Review the exact merge direction.").classes('text-sm text-slate-200')
            ui.label(
                f'{sum(refs.values())} operational reference(s) will move. '
                f'{preview.get("overlapping_hunts", 0)} overlapping hunt enrollment(s) will be consolidated.'
            ).classes('text-xs text-slate-400')
            if preview.get("fields_filled"):
                ui.label('Fields filled: ' + ', '.join(preview["fields_filled"])).classes('text-xs text-teal-300')
            if preview.get("identity_warning"):
                ui.label('No strong automatic identity signal matched. Verify these are the same person.').classes(
                    'text-xs text-orange-300 font-medium'
                )
            ui.label(
                f'#{source["id"]} remains archived for provenance. This merge can be undone for seven days.'
            ).classes('text-xs text-slate-400')
            with ui.row().classes('w-full justify-end gap-2 mt-2'):
                def cancel_merge():
                    cancel_approval(int(pending["approval_id"]), session_id=approval_session)
                    confirm_dialog.close()

                def confirm_merge():
                    merged = approve_and_dispatch(
                        int(pending["approval_id"]),
                        session_id=approval_session,
                        actor_type="ui",
                    )
                    if not merged.success:
                        ui.notify(merged.error or "Candidate merge failed.", type="negative")
                        return
                    ui.notify(
                        f'Merged into {survivor["full_name"]}. Undo is available for seven days.',
                        type="positive",
                    )
                    confirm_dialog.close()
                    review_dialog.close()
                    selected_candidate_id["value"] = survivor["id"]
                    refresh_view_ref["fn"]()

                ui.button('Cancel', on_click=cancel_merge).props('flat').classes('text-slate-400')
                ui.button('Merge Candidates', icon='merge', on_click=confirm_merge).props('color=orange no-caps')
        confirm_dialog.open()

    def confirm_archive_candidate(cid: int, name: str):
        with ui.dialog() as dialog, ui.card().classes('p-6 th-card border border-red-500/30 gap-4'):
            ui.label(f'Archive Candidate "{name}"?').classes('text-lg font-bold text-slate-100')
            ui.label('This hides the candidate from active views and can be undone for seven days.').classes('text-xs text-slate-400')
            with ui.row().classes('w-full justify-end gap-2'):
                ui.button('Cancel', on_click=dialog.close).props('flat').classes('text-slate-400')
                def do_del():
                    try:
                        result = dispatch_action(
                            "candidates.archive",
                            {"candidate_id": cid},
                            actor_type="ui",
                            session_id=f"candidate_{cid}",
                        )
                        if not result.success:
                            ui.notify(result.error or 'Archive failed.', type='negative')
                            return
                        ui.notify(f'Candidate "{name}" archived. Undo is available for seven days.', type='info')
                        dialog.close()
                        refresh_view_ref["fn"]()
                    except Exception as e:
                        ui.notify(f"Error: {e}", type="negative")
                ui.button('Archive', color='red', on_click=do_del).classes('bg-red-600 text-white text-xs px-4 py-2 rounded')
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
                        result = dispatch_action(
                            "candidates.create",
                            {
                                "full_name": name_in.value.strip(),
                                "current_title": title_in.value.strip() or None,
                                "current_company": company_in.value.strip() or None,
                                "email": email_in.value.strip() or None,
                                "location": loc_in.value.strip() or None,
                                "experience_years": float(exp_in.value) if exp_in.value is not None else None,
                                "skills": skills_list,
                                "summary": summary_in.value.strip() or None,
                            },
                            actor_type="ui",
                            session_id="candidate_create",
                        )
                        if not result.success:
                            ui.notify(result.error or 'Candidate creation failed.', type='negative')
                            return
                        if not (result.data or {}).get("changed"):
                            ui.notify((result.data or {}).get("message") or 'Candidate already exists.', type='warning')
                            selected_candidate_id["value"] = (result.data or {}).get("candidate_id")
                            dialog.close()
                            refresh_view_ref["fn"]()
                            return
                        ui.notify('Candidate created. Undo is available for seven days.', type='positive')
                        dialog.close()
                        refresh_view_ref["fn"]()
                    except Exception as e:
                        ui.notify(f"Error: {e}", type="negative")

                ui.button('Save Candidate', icon='save', on_click=save).classes('th-teal-btn')
        dialog.open()

    def set_candidate_status(candidate_id: int, status: str, candidate_name: str):
        with SessionFactory() as db:
            updated = update_candidate(db, candidate_id, status=status)
        if not updated:
            ui.notify(f'Could not update {candidate_name}.', type='negative')
            return
        ui.notify(f'{candidate_name} moved to {status}.', type='positive')
        refresh_view_ref["fn"]()

    def candidate_skills(candidate) -> list[str]:
        if not candidate.profile or not candidate.profile.skills_json:
            return []
        try:
            parsed = json.loads(candidate.profile.skills_json)
            return [str(skill).strip() for skill in parsed if str(skill).strip()]
        except (TypeError, ValueError, json.JSONDecodeError):
            return []

    def experience_period(experience) -> str:
        start = experience.start_date or 'Date unavailable'
        end = 'Present' if experience.is_current else (experience.end_date or 'Date unavailable')
        return f'{start} - {end}'

    def select_candidate(candidate_id: int):
        selected_candidate_id["value"] = candidate_id
        refresh_view_ref["fn"]()

    with ui.column().classes('w-full gap-0 th-candidates-page'):
        # Page Title Header
        with ui.row().classes('w-full justify-between items-center gap-5 mb-[22px]'):
            with ui.column().classes('gap-0'):
                ui.label('Talent intelligence').classes('th-ey')
                ui.label('Candidate Database').classes('th-title')
                ui.label('Search, score and manage your global talent pool.').classes('th-muted')

            with ui.row().classes('items-center gap-3'):
                ui.button(
                    'Duplicates', icon='content_copy',
                    on_click=open_duplicate_review,
                ).classes('th-slate-btn')

                ui.button(
                    'LlamaIndex Q&A', icon='psychology',
                    on_click=open_rag_qa_dialog
                ).classes('th-slate-btn')

                ui.button(
                    '＋ New',
                    on_click=open_create_candidate_dialog
                ).classes('th-primary-btn')

        # Search and filter toolbar
        with ui.element('section').classes('th-candidate-toolbar'):
            mode_toggle = ui.toggle(
                options={'keyword': 'Keyword', 'vector': 'Semantic'},
                value='keyword',
                on_change=lambda e: set_search_mode(e.value),
            ).props('dense no-caps toggle-color=teal-9').classes('th-candidate-mode-toggle')
            status_toggle = ui.toggle(
                options=['All', 'Active', 'Passive', 'Placed', 'Archived'],
                value='All',
                on_change=lambda e: set_status_filter(e.value),
            ).props('dense no-caps toggle-color=teal-9').classes('th-candidate-status-toggle')
            search_input = ui.input(
                placeholder='Search candidates by name, role, skill, or location'
            ).classes('th-candidate-search').props('dense dark outlined clearable')

        # Semantic Search Banner / Info when vector mode is selected
        search_banner = ui.element('div').classes('w-full')

        candidates_container = ui.column().classes('w-full gap-0')

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

                hunt_labels = get_hunt_labels_for_candidates(
                    db, [c.id for c, _ in display_cands]
                )
                hunt_ids_by_title = {hunt.title.strip().lower(): hunt.id for hunt in list_hunts(db)}

                with candidates_container:
                    if not display_cands:
                        with ui.element('div').classes('w-full min-h-[420px] border border-slate-800 rounded-lg items-center justify-center text-center gap-4 flex flex-col'):
                            ui.icon('person_search', size='48px', color='slate-500')
                            ui.label('No Candidates Found').classes('th-subheading text-slate-100')
                            ui.label('No candidate profiles match your query or selected status filters.').classes('th-body text-slate-400 max-w-md')
                            ui.button(
                                'Add First Candidate', icon='person_add',
                                on_click=open_create_candidate_dialog
                            ).classes('th-teal-btn mt-2')
                        return

                    visible_ids = {candidate.id for candidate, _ in display_cands}
                    if selected_candidate_id["value"] not in visible_ids:
                        selected_candidate_id["value"] = display_cands[0][0].id
                    selected_candidate, selected_score = next(
                        item for item in display_cands
                        if item[0].id == selected_candidate_id["value"]
                    )

                    with ui.element('section').classes('th-candidate-workspace'):
                        with ui.element('aside').classes('th-candidate-list-pane'):
                            with ui.row().classes('th-candidate-list-header'):
                                with ui.column().classes('gap-0 min-w-0'):
                                    ui.label('Candidate pool').classes('text-sm font-semibold text-slate-100')
                                    ui.label(
                                        f'{len(display_cands)} result{"s" if len(display_cands) != 1 else ""} · {selected_status["value"]}'
                                    ).classes('text-[10px] text-slate-500')
                                ui.label(
                                    f'{sum(1 for candidate, _ in display_cands if candidate.status == "Active")} shortlisted'
                                ).classes('th-candidate-count')

                            with ui.column().classes('th-candidate-list custom-scrollbar'):
                                for candidate, match_score in display_cands:
                                    candidate_id = candidate.id
                                    skills = candidate_skills(candidate)
                                    related_hunts = hunt_labels.get(candidate_id, [])
                                    is_rogue = ROGUE_TAG.lower() in {
                                        (tag.tag_name or '').lower() for tag in (candidate.tags or [])
                                    }
                                    selected = candidate_id == selected_candidate_id["value"]
                                    item_classes = 'th-candidate-list-item'
                                    if selected:
                                        item_classes += ' th-candidate-list-item-selected'
                                    if is_rogue:
                                        item_classes += ' th-candidate-list-item-rogue'

                                    with ui.element('div').classes(item_classes).on(
                                        'click', lambda _, cid=candidate_id: select_candidate(cid)
                                    ):
                                        with ui.row().classes('w-full items-start gap-3 flex-nowrap'):
                                            ui.avatar(
                                                candidate.full_name[0].upper() if candidate.full_name else '?',
                                                color='teal-9', text_color='teal-2', size='38px',
                                            ).classes('font-bold shrink-0')
                                            with ui.column().classes('grow min-w-0 gap-0'):
                                                with ui.row().classes('w-full items-center gap-1.5 flex-nowrap'):
                                                    ui.label(candidate.full_name).classes('th-candidate-row-name')
                                                    if candidate.linkedin_url:
                                                        ui.link('in', candidate.linkedin_url, new_tab=True).classes('th-linkedin-mark').tooltip('Open LinkedIn profile')
                                                    if match_score is not None:
                                                        ui.label(f'{match_score:.0f}% match').classes('th-candidate-row-score')
                                                    elif candidate.experience_years is not None:
                                                        ui.label(f'{candidate.experience_years:g} yrs').classes('th-candidate-row-score')
                                                ui.label(candidate.current_title or 'Role unavailable').classes('th-candidate-row-role')
                                                ui.label(
                                                    ' · '.join(filter(None, [candidate.current_company, candidate.location]))
                                                    or 'Company and location unavailable'
                                                ).classes('th-candidate-row-meta')

                                        with ui.row().classes('th-candidate-row-footer'):
                                            if is_rogue:
                                                ui.label('Mismatch').classes('th-candidate-mini-tag th-candidate-mini-tag-warn')
                                            for skill in skills[:2]:
                                                ui.label(skill).classes('th-candidate-mini-tag')
                                            if len(skills) > 2:
                                                ui.label(f'+{len(skills) - 2} skills').classes('th-candidate-row-more')
                                            if related_hunts:
                                                ui.label(related_hunts[0]).classes('th-candidate-hunt-label')

                        candidate = selected_candidate
                        candidate_id = candidate.id
                        skills = candidate_skills(candidate)
                        related_hunts = hunt_labels.get(candidate_id, [])
                        tag_names = {(tag.tag_name or '').lower() for tag in (candidate.tags or [])}
                        is_rogue = ROGUE_TAG.lower() in tag_names
                        insight = (
                            candidate.profile.ai_evaluation
                            if candidate.profile and candidate.profile.ai_evaluation
                            else candidate.profile.summary
                            if candidate.profile and candidate.profile.summary
                            else f'{candidate.full_name} is currently listed as {candidate.current_title or "a candidate"}. Review the evidence below before making a decision.'
                        )

                        with ui.element('article').classes('th-candidate-detail-pane custom-scrollbar'):
                            with ui.element('header').classes('th-candidate-detail-header'):
                                with ui.row().classes('th-candidate-profile-top'):
                                    with ui.row().classes('th-candidate-profile-identity'):
                                        ui.avatar(
                                            candidate.full_name[0].upper() if candidate.full_name else '?',
                                            color='teal-9', text_color='teal-2', size='50px',
                                        ).classes('text-base font-bold shrink-0')
                                        with ui.column().classes('gap-0 min-w-0'):
                                            with ui.row().classes('items-center gap-2 flex-wrap'):
                                                ui.label(candidate.full_name).classes('th-candidate-profile-name')
                                                ui.label(candidate.status).classes(
                                                    'th-candidate-status-pill '
                                                    + ('th-candidate-status-active' if candidate.status == 'Active' else 'th-candidate-status-passive')
                                                )
                                                if is_rogue:
                                                    ui.label('Skills mismatch').classes('th-candidate-status-pill th-candidate-status-mismatch')
                                            ui.label(candidate.current_title or 'Role unavailable').classes('th-candidate-profile-role')
                                            ui.label(
                                                f'{candidate.current_company or "Company unavailable"} · {candidate.location or "Location unavailable"}'
                                            ).classes('th-candidate-profile-meta')
                                    with ui.row().classes('th-candidate-header-actions'):
                                        ui.button(
                                            icon='campaign',
                                            on_click=lambda _, cid=candidate_id, name=candidate.full_name, hunts=list(related_hunts): open_assign_hunt_dialog(cid, name, hunts),
                                        ).props('flat round dense').classes('th-candidate-icon-btn text-teal-300').tooltip('Add to Talent Hunt')
                                        ui.button(
                                            icon='open_in_new',
                                            on_click=lambda _, cid=candidate_id: ui.navigate.to(f'/candidates/{cid}'),
                                        ).props('flat round dense').classes('th-candidate-icon-btn text-slate-300').tooltip('Open 360° profile')
                                        ui.button(
                                            icon='delete_outline',
                                            on_click=lambda _, cid=candidate_id, name=candidate.full_name: confirm_archive_candidate(cid, name),
                                        ).props('flat round dense').classes('th-candidate-icon-btn text-slate-500 hover:text-red-400').tooltip('Archive candidate')

                                with ui.row().classes('th-candidate-profile-facts'):
                                    if candidate.experience_years is not None:
                                        with ui.element('span').classes('th-candidate-fact'):
                                            ui.icon('work_history', size='15px', color='teal-4')
                                            ui.label(f'{candidate.experience_years:g} years experience')
                                    if candidate.linkedin_url:
                                        ui.link('LinkedIn', candidate.linkedin_url, new_tab=True).classes('th-candidate-fact th-candidate-fact-link').tooltip('Open LinkedIn profile')
                                    if candidate.github_url:
                                        ui.link('GitHub', candidate.github_url, new_tab=True).classes('th-candidate-fact th-candidate-fact-link').tooltip('Open GitHub profile')
                                    for hunt_title in related_hunts:
                                        _render_tag(
                                            hunt_title, 'teal-9',
                                            _tag_target(hunt_title, candidate, hunt_ids_by_title),
                                            'th-candidate-fact th-candidate-fact-hunt',
                                        )

                            with ui.element('section').classes('th-candidate-action-band'):
                                with ui.element('div').classes('th-contact-grid'):
                                    with ui.element('div').classes('th-contact-field'):
                                        ui.icon('phone', size='17px', color='teal-4')
                                        with ui.column().classes('gap-0 min-w-0'):
                                            ui.label('Phone').classes('th-contact-label')
                                            ui.label(candidate.phone or 'Not available').classes('th-contact-value')
                                    with ui.element('div').classes('th-contact-field'):
                                        ui.icon('mail', size='17px', color='teal-4')
                                        with ui.column().classes('gap-0 min-w-0'):
                                            ui.label('Email').classes('th-contact-label')
                                            ui.label(candidate.email or 'Not available').classes('th-contact-value')

                                with ui.element('div').classes('th-decision-grid'):
                                    ui.button(
                                        'Shortlist', icon='check',
                                        on_click=lambda _, cid=candidate_id, name=candidate.full_name: set_candidate_status(cid, 'Active', name),
                                    ).props('unelevated no-caps').classes('th-decision-shortlist').style(
                                        'background-color: #0b8066 !important; color: #ffffff !important;'
                                    )
                                    ui.button(
                                        'Maybe', icon='schedule',
                                        on_click=lambda _, cid=candidate_id, name=candidate.full_name: set_candidate_status(cid, 'Passive', name),
                                    ).props('unelevated no-caps').classes('th-decision-maybe').style(
                                        'background-color: #3a2d13 !important; color: #f0c96e !important;'
                                    )
                                    ui.button(
                                        'Clear mismatch' if is_rogue else 'Mismatch',
                                        icon='undo' if is_rogue else 'close',
                                        on_click=lambda _, cid=candidate_id, name=candidate.full_name, rogue=is_rogue: open_rogue_dialog(cid, name, rogue),
                                    ).props('unelevated no-caps').classes('th-decision-mismatch').style(
                                        'background-color: #321923 !important; color: #ee9ba4 !important;'
                                    )

                            with ui.element('section').classes('th-insight-section'):
                                with ui.row().classes('th-candidate-section-heading'):
                                    with ui.row().classes('items-center gap-2'):
                                        ui.icon('auto_awesome', size='19px', color='teal-4')
                                        ui.label('Match insight').classes('th-candidate-section-title')
                                    if selected_score is not None:
                                        ui.label(f'{selected_score:.1f}% semantic match').classes('th-candidate-match-score')
                                ui.markdown(insight).classes('th-insight-copy')

                                with ui.element('div').classes('th-evidence-grid'):
                                    if candidate.experience_years is not None:
                                        with ui.element('div').classes('th-evidence-card'):
                                            ui.label(f'{candidate.experience_years:g} years experience').classes('th-evidence-value')
                                            ui.label(
                                                f'{len(candidate.experiences)} verified employment record(s)' if candidate.experiences else 'Approved profile value'
                                            ).classes('th-evidence-source')
                                    for skill in skills[:6]:
                                        with ui.element('div').classes('th-evidence-card'):
                                            ui.label(skill).classes('th-evidence-value')
                                            ui.label('Stored profile skill').classes('th-evidence-source')
                                    if not skills and candidate.experience_years is None:
                                        with ui.element('div').classes('th-evidence-empty'):
                                            ui.icon('manage_search', size='20px', color='slate-500')
                                            ui.label('No structured evidence stored yet.').classes('text-[11px] text-slate-500')

                            with ui.element('section').classes('th-profile-history'):
                                with ui.element('div').classes('th-history-column'):
                                    with ui.row().classes('th-history-heading'):
                                        ui.icon('business_center', size='18px', color='slate-400')
                                        ui.label('Experience').classes('text-sm font-semibold text-slate-100')
                                        ui.label(str(len(candidate.experiences))).classes('th-history-count')
                                    if candidate.experiences:
                                        for experience in candidate.experiences:
                                            with ui.element('div').classes('th-history-item'):
                                                ui.label(experience.title).classes('th-history-role')
                                                ui.label(experience.company).classes('th-history-org')
                                                ui.label(experience_period(experience)).classes('th-history-period')
                                    else:
                                        with ui.element('div').classes('th-history-empty'):
                                            ui.icon('work_off', size='20px', color='slate-600')
                                            ui.label('No experience records stored').classes('text-[11px] text-slate-500')
                                with ui.element('div').classes('th-history-column'):
                                    with ui.row().classes('th-history-heading'):
                                        ui.icon('school', size='18px', color='slate-400')
                                        ui.label('Education').classes('text-sm font-semibold text-slate-100')
                                        ui.label(str(len(candidate.educations))).classes('th-history-count')
                                    if candidate.educations:
                                        for education in candidate.educations:
                                            with ui.element('div').classes('th-history-item'):
                                                ui.label(education.degree or 'Education').classes('th-history-role')
                                                ui.label(education.institution).classes('th-history-org')
                                                if education.field_of_study:
                                                    ui.label(education.field_of_study).classes('th-history-period')
                                    else:
                                        with ui.element('div').classes('th-history-empty'):
                                            ui.icon('school', size='20px', color='slate-600')
                                            ui.label('No education records stored').classes('text-[11px] text-slate-500')

        refresh_view_ref["fn"] = refresh_view
        search_input.on('update:model-value', lambda e: refresh_view())
        refresh_view()

    def open_rag_qa_dialog():
        with ui.dialog() as dialog, ui.card().classes('w-full max-w-2xl p-6 th-card border border-indigo-500/40 gap-4'):
            with ui.row().classes('items-center gap-3'):
                ui.icon('psychology', size='md', color='indigo-4')
                with ui.column().classes('gap-0'):
                    ui.label('Candidate Evidence Search').classes('text-xl font-bold text-slate-100')
                    ui.label('Ask the talent pool and inspect the profile evidence behind each answer.').classes('text-xs text-slate-400')

            qa_input = ui.input(
                placeholder='e.g., "Who has the best experience in vector search and local models?"'
            ).classes('w-full').props('dark outlined dense')

            output_area = ui.column().classes('w-full gap-3 p-4 bg-slate-950/80 border border-teal-900/30 rounded-lg min-h-[150px]')
            with output_area:
                ui.label('Enter a question to search skills, experience, notes, resumes, and saved profiles.').classes('text-xs text-slate-500 italic')

            def run_rag_query():
                q_text = qa_input.value.strip()
                if not q_text:
                    ui.notify('Please enter a question.', type='warning')
                    return

                output_area.clear()
                with output_area:
                    with ui.row().classes('items-center gap-2 text-teal-400 text-xs'):
                        ui.spinner(size='sm', color='teal')
                        ui.label('Retrieving and ranking candidate evidence...')

                with SessionFactory() as db:
                    result = candidate_rag.query_candidate_database(query=q_text, db=db)

                output_area.clear()
                with output_area:
                    ui.label('AI Answer:').classes('text-xs font-bold text-teal-400')
                    ui.markdown(result["answer"]).classes('text-sm text-slate-200 leading-relaxed')

                    if result.get("sources"):
                        ui.separator().classes('bg-teal-900/30 my-2')
                        retrieval = result.get('retrieval') or {}
                        ui.label(
                            f"Evidence sources · {retrieval.get('candidates_retrieved', len(result['sources']))} candidates"
                        ).classes('text-[11px] font-semibold text-slate-400')
                        for src in result["sources"]:
                            score_str = f"{src.get('relevance_score')}%" if src.get("relevance_score") is not None else ""
                            with ui.row().classes('w-full items-start gap-2 py-2 border-b border-slate-800/70'):
                                ui.button(
                                    icon='person_search',
                                    on_click=lambda cid=src['id']: ui.navigate.to(f'/candidates/{cid}'),
                                ).props('flat round dense').classes('text-teal-400')
                                with ui.column().classes('grow gap-1'):
                                    with ui.row().classes('w-full justify-between gap-2'):
                                        ui.label(f"#{src['id']} {src['full_name']}").classes('text-xs font-semibold text-slate-200')
                                        if score_str:
                                            ui.label(score_str).classes('text-[10px] text-teal-400')
                                    if src.get('current_title'):
                                        ui.label(src['current_title']).classes('text-[10px] text-slate-500')
                                    for evidence in (src.get('evidence') or [])[:3]:
                                        ui.label(evidence.get('label') or 'Evidence').classes('text-[10px] font-semibold text-amber-300')
                                        ui.label(evidence.get('snippet') or '').classes('text-[11px] text-slate-400 leading-relaxed')

            with ui.row().classes('w-full justify-between items-center pt-2'):
                ui.button('Close', on_click=dialog.close).props('flat').classes('text-slate-400 text-xs')
                ui.button('Search evidence', icon='send', color='indigo', on_click=run_rag_query).classes('bg-indigo-600 hover:bg-indigo-500 text-white text-xs px-4 py-2 rounded')

        dialog.open()


def candidates_page():
    create_layout(render_candidates)
