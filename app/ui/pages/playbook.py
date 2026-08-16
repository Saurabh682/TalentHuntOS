"""Global Sourcing Playbook — shared Keep/Pass learnings and insights."""

from types import SimpleNamespace

from nicegui import ui

from app.actions.api import dispatch_action
from app.ui.layout import create_layout
from app.infrastructure.db import init_db


def _author() -> str:
    try:
        return (ui.app.storage.user.get("playbook_author") or "Recruiter").strip() or "Recruiter"
    except Exception:
        return "Recruiter"


def render_playbook():
    init_db()

    filters = {"type": "All", "platform": "All", "role": "", "search": ""}
    list_box_ref = {"el": None}

    def refresh():
        list_box = list_box_ref["el"]
        if list_box is None:
            return
        list_box.clear()
        with list_box:
            result = dispatch_action(
                "playbook.list",
                {
                    "entry_type": filters["type"],
                    "role": filters["role"] or None,
                    "platform": filters["platform"],
                    "search": filters["search"] or None,
                    "limit": 150,
                },
                actor_type="ui",
                session_id="playbook",
            )
            if not result.success:
                ui.notify(result.error or 'Could not load Playbook.', type='negative')
                return
            entries = [SimpleNamespace(**row) for row in (result.data or {}).get("entries", [])]
            if not entries:
                with ui.card().classes('w-full p-10 th-card items-center text-center gap-2'):
                    ui.icon('menu_book', size='40px', color='slate-500')
                    ui.label('No playbook entries yet').classes('th-subheading text-slate-100')
                    ui.label('Use Keep / Pass on Sourced pipeline cards, or add an insight.').classes('th-body text-slate-400')
                return
            for e in entries:
                _render_entry_card(e)

    def open_insight_dialog():
        with ui.dialog() as dialog, ui.card().classes('w-full max-w-lg p-5 th-card gap-3'):
            ui.label('Add playbook insight').classes('text-lg font-bold text-slate-100')
            outcome = ui.toggle(
                {'worked': 'What worked', 'didnt_work': "What didn't"},
                value='worked',
            ).classes('w-full')
            role_f = ui.input(placeholder='Role context (e.g. BD Executive)').classes('w-full').props('dark outlined dense')
            plat_f = ui.select(
                options=['', 'linkedin', 'naukri', 'web'],
                value='',
                label='Platform',
            ).classes('w-full').props('dark outlined dense')
            query_f = ui.input(placeholder='Query / boolean that worked or failed').classes('w-full').props('dark outlined dense')
            note_f = ui.textarea(placeholder='What should the team remember?').classes('w-full').props('dark outlined dense')

            with ui.row().classes('w-full justify-end gap-2'):
                ui.button('Cancel', on_click=dialog.close).props('flat').classes('text-slate-400')

                def save():
                    note = (note_f.value or "").strip()
                    if not note:
                        ui.notify('Note is required for an insight.', type='negative')
                        return
                    result = dispatch_action(
                        "playbook.insights.add",
                        {
                            "worked": outcome.value == 'worked',
                            "note": note,
                            "role_context": (role_f.value or "").strip() or None,
                            "platform": (plat_f.value or "").strip() or None,
                            "query_text": (query_f.value or "").strip() or None,
                            "author_name": _author(),
                        },
                        actor_type="ui",
                        session_id="playbook",
                    )
                    if not result.success:
                        ui.notify(result.error or 'Could not add insight.', type='negative')
                        return
                    ui.notify('Insight added to shared playbook.', type='positive')
                    dialog.close()
                    refresh()

                ui.button('Save insight', icon='save', on_click=save).classes('th-primary-btn')
        dialog.open()

    with ui.column().classes('w-full gap-4'):
        with ui.row().classes('w-full justify-between items-end flex-wrap gap-3'):
            with ui.column().classes('gap-0'):
                ui.label('Sourcing').classes('th-ey')
                ui.label('Playbook').classes('th-title')
                ui.label('Shared learnings — what made the list, what didn’t, and which queries worked.').classes('th-muted')

            with ui.row().classes('items-center gap-2'):
                author_in = ui.input(
                    label='Author',
                    value=_author(),
                ).classes('w-40').props('dark outlined dense')

                def save_author():
                    name = (author_in.value or "").strip() or "Recruiter"
                    try:
                        ui.app.storage.user["playbook_author"] = name
                    except Exception:
                        pass
                    ui.notify(f'Author set to {name}', type='info')

                author_in.on('blur', save_author)
                ui.button('Add insight', icon='lightbulb', on_click=open_insight_dialog).classes('th-primary-btn')

        with ui.row().classes('w-full items-center gap-2 flex-wrap'):
            type_sel = ui.select(
                options=['All', 'Kept', 'Passed', 'Insights'],
                value='All',
                label='Type',
            ).classes('w-36').props('dark outlined dense')
            platform_sel = ui.select(
                options=['All', 'linkedin', 'naukri', 'web'],
                value='All',
                label='Platform',
            ).classes('w-36').props('dark outlined dense')
            role_in = ui.input(placeholder='Filter by role…').classes('w-48').props('dark outlined dense')
            search_in = ui.input(placeholder='Search notes, queries, names…').classes('grow').props('dark outlined dense')

            def apply_filters():
                filters["type"] = type_sel.value or "All"
                filters["platform"] = platform_sel.value or "All"
                filters["role"] = (role_in.value or "").strip()
                filters["search"] = (search_in.value or "").strip()
                refresh()

            for w in (type_sel, platform_sel):
                w.on('update:model-value', lambda e: apply_filters())
            role_in.on('update:model-value', lambda e: apply_filters())
            search_in.on('update:model-value', lambda e: apply_filters())

        list_box_ref["el"] = ui.column().classes('w-full gap-3 mt-2')
        refresh()


def _render_entry_card(e):
    et = e.entry_type
    if et == "keep":
        badge, color = "Kept", "teal"
    elif et == "pass":
        badge, color = "Passed", "orange"
    else:
        badge = "Worked" if e.insight_outcome == "worked" else "Didn't work"
        color = "positive" if e.insight_outcome == "worked" else "negative"

    with ui.card().classes('w-full p-4 th-card border border-teal-900/30 gap-2'):
        with ui.row().classes('w-full justify-between items-start flex-wrap gap-2'):
            with ui.row().classes('items-center gap-2 flex-wrap'):
                ui.badge(badge, color=color).classes('text-[10px]')
                if e.role_context:
                    ui.label(e.role_context).classes('text-sm font-semibold text-slate-100')
                if e.platform:
                    ui.badge(e.platform, color='slate-800').classes('text-[10px] text-teal-300')
            when = str(e.created_at or "").replace("T", " ")[:16]
            ui.label(f"{e.author_name} · {when}").classes('text-[10px] text-slate-500')

        if e.candidate_name:
            ui.label(
                f"{e.candidate_name}"
                + (f" — {e.candidate_title}" if e.candidate_title else "")
            ).classes('text-xs text-slate-300')

        if e.query_text:
            ui.label(f"Query: {e.query_text}").classes('text-xs text-slate-400 font-mono')

        if e.hunt_title:
            ui.label(f"Hunt: {e.hunt_title}").classes('text-[11px] text-teal-400/90')

        if e.note:
            ui.label(e.note).classes('text-sm text-slate-200 mt-1')


def playbook_page():
    create_layout(lambda: render_playbook(), active_path="/playbook")
