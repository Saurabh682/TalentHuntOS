"""Three-panel layout for TalentHunt OS."""

from nicegui import ui
from app.ui.theme import apply_theme
from app.ui.panels.copilot_panel import render_copilot_panel

def create_layout(main_content_fn, active_path: str = "/"):
    """Render the standard 3-panel shell layout matching Recruiter OS design.
    
    Panel 1 (Left): Navigation Sidebar
    Panel 2 (Center): Main Content Area
    Panel 3 (Right): Copilot Chat & Voice Panel
    """
    apply_theme()
    
    # Try getting active path from client context
    current_path = active_path
    try:
        if hasattr(ui.context, 'client') and ui.context.client and ui.context.client.page:
            current_path = ui.context.client.page.path
    except Exception:
        pass

    with ui.row().classes('w-full h-screen no-wrap gap-0 th-shell overflow-hidden bg-[#050607]'):
        # Panel 1: Left Navigation Sidebar
        with ui.column().classes('w-52 py-5 px-0 shrink-0 h-screen overflow-y-auto border-r border-[#1E2226] flex-nowrap custom-scrollbar bg-[#0E1113] justify-between'):
            with ui.column().classes('w-full gap-0'):
                # Brand Header
                with ui.row().classes('items-center gap-2.5 px-5 py-4 mb-2 w-full'):
                    with ui.element('div').classes('w-8 h-8 rounded-lg bg-[#10241D] border border-[#3ED9A6]/30 flex items-center justify-center shrink-0'):
                        ui.icon('hexagon', size='18px').classes('text-[#3ED9A6]')
                    ui.label('TalentHunt').classes('text-sm font-bold text-[#E7E9EA] tracking-tight')
                
                # Nav links matching user mockup
                nav_items = [
                    ('Dashboard', 'widgets', '/'),
                    ('Hunts', 'track_changes', '/hunts'),
                    ('Candidates', 'group', '/candidates'),
                    ('Pipeline', 'view_kanban', '/pipeline'),
                    ('Comms', 'chat_bubble_outline', '/communications'),
                    ('Analytics', 'show_chart', '/analytics'),
                    ('Settings', 'settings', '/settings'),
                ]
                
                with ui.column().classes('w-full gap-0.5'):
                    for label, icon, path in nav_items:
                        is_active = (current_path == path or (path != '/' and current_path.startswith(path)))
                        if is_active:
                            active_cls = 'bg-[#121A18] text-[#FFFFFF] font-semibold border-l-[3px] border-[#3ED9A6]'
                            icon_cls = 'text-[#3ED9A6]'
                        else:
                            active_cls = 'text-[#8A9096] hover:bg-[#151A1D]/60 hover:text-[#EDEFEF] border-l-[3px] border-transparent'
                            icon_cls = 'text-[#8A9096]'
                        
                        with ui.row().classes(f'w-full items-center px-4 py-2.5 cursor-pointer transition-all duration-150 {active_cls} gap-3').on('click', lambda p=path: ui.navigate.to(p)):
                            ui.icon(icon, size='18px').classes(icon_cls)
                            ui.label(label).classes('text-[13px]')

            # System Status Indicator
            with ui.row().classes('items-center gap-2 px-5 py-3 text-[11px] text-[#6B7278] border-t border-[#1E2226]/40 mt-auto'):
                ui.element('span').classes('w-1.5 h-1.5 rounded-full bg-[#3ED9A6] animate-pulse')
                ui.label('AI engine ready')
        
        # Panel 2: Center Main Content Area
        with ui.column().classes('col grow p-6 h-screen overflow-y-auto w-full gap-6 custom-scrollbar flex-nowrap bg-[#0B0D0F]'):
            main_content_fn()
        
        # Panel 3: Right Copilot Panel
        with ui.column().classes('w-80 p-4 shrink-0 th-copilot-panel h-screen max-h-screen flex flex-col justify-between overflow-hidden border-l border-[#1E2226] gap-3 flex-nowrap bg-[#0E1113]'):
            render_copilot_panel()
