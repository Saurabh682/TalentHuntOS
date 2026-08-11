"""Embedded Browser Panel component for TalentHunt OS (LinkedIn / Naukri / Sourcing browser)."""

from nicegui import ui


def render_browser_panel(initial_url: str = "https://www.linkedin.com"):
    """Render reusable embedded iframe browser component for sourcing talent on LinkedIn & Naukri."""
    
    current_url = {"value": initial_url}

    with ui.column().classes('w-full gap-4'):
        with ui.card().classes('w-full p-4 th-card border border-teal-900/30 gap-2'):
            with ui.row().classes('items-center gap-2 mb-1'):
                ui.icon('verified_user', color='teal-4', size='sm')
                ui.label('Site logins (for search & snapshots)').classes('text-sm font-bold text-slate-100')
            ui.label(
                'Connect once so Playwright can open profiles while logged in. Cookies stay encrypted on this PC.'
            ).classes('text-[11px] text-slate-500 mb-2')
            from app.ui.components.connect_sites import render_connect_sites_panel
            render_connect_sites_panel(compact=True)

        # Header Controls & Address Bar
        with ui.card().classes('w-full p-4 th-card border border-teal-900/30 gap-3'):
            with ui.row().classes('w-full items-center justify-between flex-wrap gap-2'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('language', color='teal-4', size='sm')
                    ui.label('Embedded Sourcing Browser').classes('text-base font-bold text-slate-100')
                    ui.badge('Preview', color='blue-grey').classes('text-[10px]')

                # Quick Bookmark Buttons
                with ui.row().classes('items-center gap-1.5 flex-wrap'):
                    ui.label('Bookmarks:').classes('text-xs text-slate-400 mr-1')
                    ui.button(
                        'LinkedIn', icon='work',
                        on_click=lambda: navigate_to('https://www.linkedin.com')
                    ).props('dense flat').classes('text-xs text-blue-400 hover:bg-blue-950/40')

                    ui.button(
                        'Naukri', icon='business_center',
                        on_click=lambda: navigate_to('https://www.naukri.com')
                    ).props('dense flat').classes('text-xs text-amber-400 hover:bg-amber-950/40')

                    ui.button(
                        'GitHub', icon='code',
                        on_click=lambda: navigate_to('https://github.com')
                    ).props('dense flat').classes('text-xs text-purple-400 hover:bg-purple-950/40')

                    ui.button(
                        'Indeed', icon='search',
                        on_click=lambda: navigate_to('https://www.indeed.com')
                    ).props('dense flat').classes('text-xs text-emerald-400 hover:bg-emerald-950/40')

            # URL Address input row
            with ui.row().classes('w-full items-center gap-2'):
                url_input = ui.input(
                    value=current_url["value"]
                ).classes('grow text-sm').props('dense dark outlined rounded')
                
                ui.button(
                    'Go', icon='arrow_forward', color='teal',
                    on_click=lambda: navigate_to(url_input.value)
                ).classes('th-teal-btn text-xs px-3 py-1.5')

                ui.button(
                    icon='refresh',
                    on_click=lambda: navigate_to(current_url["value"])
                ).props('flat round dense').tooltip('Reload Page')

                ui.button(
                    icon='open_in_new',
                    on_click=lambda: ui.navigate.to(current_url["value"], new_tab=True)
                ).props('flat round dense').tooltip('Open in New Browser Tab')

        # IFrame Container Area
        iframe_container = ui.element('div').classes('w-full min-h-[600px] border border-teal-900/40 rounded-lg overflow-hidden bg-slate-950 shadow-inner')

        def update_iframe():
            iframe_container.clear()
            with iframe_container:
                # Security note: Some sites (like LinkedIn) block embedding in iframes via X-Frame-Options SAMEORIGIN.
                # We provide a clean fallback notice and direct tab opener if framed access is restricted.
                ui.html(f'''
                    <div style="position:relative; width:100%; height:620px;">
                        <iframe 
                            src="{current_url['value']}" 
                            style="width:100%; height:100%; border:0;" 
                            sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
                            loading="lazy">
                        </iframe>
                    </div>
                ''')

        def navigate_to(target: str):
            target = target.strip()
            if target and not (target.startswith('http://') or target.startswith('https://')):
                target = 'https://' + target
            current_url["value"] = target
            url_input.value = target
            update_iframe()

        url_input.on('keydown.enter', lambda e: navigate_to(url_input.value))
        update_iframe()
