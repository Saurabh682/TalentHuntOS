"""Three-panel layout for TalentHunt OS — Modern Ocean design pack."""

from nicegui import ui
from app.ui.theme import apply_theme
from app.ui.panels.copilot_panel import render_copilot_panel

def create_layout(main_content_fn, active_path: str = "/"):
    """Render the standard 3-panel shell layout matching the Modern HTML UI.
    
    Panel 1 (Left): Navigation Sidebar
    Panel 2 (Center): Main Content Area
    Panel 3 (Right): Copilot Chat & Voice Panel
    """
    apply_theme()
    
    current_path = active_path
    try:
        if hasattr(ui.context, 'client') and ui.context.client and ui.context.client.page:
            current_path = ui.context.client.page.path
    except Exception:
        pass

    with ui.row().classes('w-full h-screen no-wrap gap-0 th-shell overflow-hidden bg-[#071019]'):
        # Panel 1: Left Navigation Sidebar
        with ui.column().classes(
            'w-[220px] py-[22px] px-[15px] shrink-0 h-screen overflow-y-auto '
            'border-r border-[#1b3040] flex-nowrap custom-scrollbar bg-[#08121d] justify-between'
        ):
            with ui.column().classes('w-full gap-0'):
                # Brand Header
                with ui.column().classes('px-[10px] pt-2 pb-7 w-full gap-1'):
                    ui.label('TalentHunt OS').classes('text-[15px] font-extrabold text-[#edf5f7] tracking-tight')
                    ui.label('AI Recruiter Copilot').classes('text-[11px] font-medium text-[#19d3c5]')

                nav_items = [
                    ('Dashboard', 'dashboard', '/'),
                    ('Hunts', 'travel_explore', '/hunts'),
                    ('Candidates', 'group', '/candidates'),
                    ('Pipeline', 'view_kanban', '/pipeline'),
                    ('Communications', 'forum', '/communications'),
                    ('Analytics', 'insights', '/analytics'),
                    ('Settings', 'settings', '/settings'),
                ]

                with ui.column().classes('w-full gap-0.5'):
                    for label, icon, path in nav_items:
                        is_active = (current_path == path or (path != '/' and current_path.startswith(path)))
                        if is_active:
                            row_cls = 'th-nav-item-active'
                            icon_cls = 'text-white'
                        else:
                            row_cls = 'th-nav-item hover:bg-[#123542]'
                            icon_cls = 'text-[#8ea4b4]'

                        with ui.row().classes(
                            f'w-full items-center px-[13px] py-[11px] cursor-pointer '
                            f'transition-all duration-150 rounded-[9px] {row_cls} gap-3'
                        ).on('click', lambda p=path: ui.navigate.to(p)):
                            ui.icon(icon, size='18px').classes(icon_cls)
                            ui.label(label).classes('text-[13px]')

            # AI Engine status
            with ui.row().classes('th-engine w-full items-center justify-between mt-auto'):
                ui.label('AI Engine')
                ui.label('● Local Ready').classes('text-[#19d3c5] font-semibold text-[11px]')

        # Panel 2: Center Main Content Area
        with ui.column().classes(
            'col grow th-main h-screen overflow-y-auto w-full gap-0 custom-scrollbar flex-nowrap bg-[#071019]'
        ):
            main_content_fn()

        # Panel 3: Right Copilot Panel
        with ui.column().classes(
            'w-[285px] p-4 shrink-0 th-copilot-panel h-screen max-h-screen flex flex-col '
            'justify-between overflow-hidden border-l border-[#1b3040] gap-3 flex-nowrap bg-[#08121d]'
        ):
            render_copilot_panel()
