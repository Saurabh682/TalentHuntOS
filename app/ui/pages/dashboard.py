"""Dashboard page for TalentHunt OS."""

from nicegui import ui
from app.ui.layout import create_layout

def render_dashboard():
    """Render the main overview dashboard."""
    with ui.column().classes('w-full gap-6'):
        # Header
        with ui.row().classes('w-full justify-between items-center'):
            with ui.column().classes('gap-1'):
                ui.label('Talent Overview').classes('text-2xl font-bold text-slate-100')
                ui.label('Active talent hunts, recent candidate matches, and AI activity.').classes('text-sm text-slate-400')
            ui.button('New Talent Hunt', icon='add', color='teal', on_click=lambda: ui.navigate.to('/hunts')).classes('th-teal-btn')
        
        # Stat summary cards
        with ui.row().classes('w-full gap-4 no-wrap'):
            with ui.card().classes('col p-4 th-card'):
                ui.label('Active Hunts').classes('text-xs text-slate-400 uppercase tracking-wider')
                ui.label('0').classes('text-3xl font-bold text-teal-400 mt-1')
                ui.label('Phase 3 pipeline ready').classes('text-xs text-slate-500 mt-1')
            
            with ui.card().classes('col p-4 th-card'):
                ui.label('Candidates Sourced').classes('text-xs text-slate-400 uppercase tracking-wider')
                ui.label('0').classes('text-3xl font-bold text-amber-400 mt-1')
                ui.label('Multi-site crawler ready').classes('text-xs text-slate-500 mt-1')
                
            with ui.card().classes('col p-4 th-card'):
                ui.label('AI Actions Today').classes('text-xs text-slate-400 uppercase tracking-wider')
                ui.label('1').classes('text-3xl font-bold text-indigo-400 mt-1')
                ui.label('Local AI initializing').classes('text-xs text-slate-500 mt-1')
        
        # Recent Activity & Quick Actions
        with ui.row().classes('w-full gap-6 no-wrap'):
            with ui.card().classes('col-8 p-5 th-card'):
                ui.label('Recent Talent Hunts').classes('text-lg font-semibold text-slate-200 mb-2')
                with ui.column().classes('w-full py-8 items-center justify-center text-slate-500'):
                    ui.icon('search_off', size='lg').classes('mb-2')
                    ui.label('No active talent hunts yet. Start a new hunt using Copilot or click New Talent Hunt.')
            
            with ui.card().classes('col-4 p-5 bg-[#121619] border border-[#1E2226] rounded-xl'):
                ui.label('Quick Actions').classes('text-base font-semibold text-[#E7E9EA] mb-3')
                with ui.column().classes('w-full gap-2'):
                    ui.button('Parse Job Description', icon='description', on_click=lambda: ui.navigate.to('/hunts')).classes('w-full justify-start th-slate-btn text-xs').props('flat no-caps')
                    ui.button('Connect AI Providers', icon='key', on_click=lambda: ui.navigate.to('/settings')).classes('w-full justify-start th-slate-btn text-xs').props('flat no-caps')
                    ui.button('Check Local AI Status', icon='memory', on_click=lambda: ui.navigate.to('/settings')).classes('w-full justify-start th-slate-btn text-xs').props('flat no-caps')

def dashboard_page():
    create_layout(render_dashboard)
