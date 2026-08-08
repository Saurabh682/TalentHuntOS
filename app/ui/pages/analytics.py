"""Analytics & Intelligence Dashboard page for TalentHunt OS."""

from datetime import datetime, timezone
from typing import Optional, Dict, Any
from nicegui import ui
from app.ui.layout import create_layout
from app.infrastructure.db import SessionFactory
from app.hunts.service import list_hunts
from app.analytics.service import get_all_analytics_data
from app.analytics.reports import generate_analytics_pdf, generate_analytics_csv


def render_analytics():
    """Render the Analytics & Intelligence Dashboard UI."""
    db = SessionFactory()
    try:
        all_hunts = list_hunts(db)
        hunt_options = {0: "All Talent Hunts"}
        for h in all_hunts:
            hunt_options[h.id] = f"{h.title} ({h.target_role or 'General'})"
    finally:
        db.close()

    # Dashboard Reactive State
    state = {
        "selected_hunt_id": 0,
        "time_range_days": 30,
        "data": {},
    }

    def fetch_data():
        h_id = None if state["selected_hunt_id"] == 0 else state["selected_hunt_id"]
        db_sess = SessionFactory()
        try:
            state["data"] = get_all_analytics_data(db_sess, hunt_id=h_id, days=state["time_range_days"])
        finally:
            db_sess.close()

    # Initial data load
    fetch_data()

    with ui.column().classes('w-full gap-0'):
        # Header & Filter Bar
        with ui.row().classes('w-full justify-between items-center flex-wrap gap-4 mb-[22px]'):
            with ui.column().classes('gap-0'):
                ui.label('Performance intelligence').classes('th-ey')
                ui.label('Analytics & Intelligence').classes('th-title')
                ui.label('Real-time recruitment funnel, velocity, outreach response and AI cost metrics.').classes('th-muted')

            with ui.row().classes('items-center gap-3 flex-wrap'):
                # Hunt Selector
                hunt_select = ui.select(
                    options=hunt_options,
                    value=state["selected_hunt_id"],
                    label="Filter Campaign",
                    on_change=lambda e: update_dashboard(selected_hunt=e.value),
                ).classes('w-64').props('outlined dense dark stack-label options-dense')

                # Time Range Selector
                time_select = ui.select(
                    options={7: "Last 7 Days", 30: "Last 30 Days", 90: "Last 90 Days"},
                    value=state["time_range_days"],
                    label="Time Range",
                    on_change=lambda e: update_dashboard(days=e.value),
                ).classes('w-48').props('outlined dense dark stack-label options-dense')

                # Export Actions
                ui.button('⇩ Export CSV', on_click=lambda: handle_export_csv()).classes('th-slate-btn')
                ui.button('PDF Report', icon='picture_as_pdf', on_click=lambda: handle_export_pdf()).classes('th-primary-btn')

        # KPI Summary Cards Grid
        kpi_container = ui.row().classes('w-full gap-[13px] flex-wrap no-wrap-md')
        
        # Charts Container
        charts_container = ui.column().classes('w-full gap-[13px] mt-[13px]')

        # Data Tables Container
        tables_container = ui.column().classes('w-full gap-[13px]')

        def render_kpi_cards():
            kpi_container.clear()
            kpi = state["data"].get("kpi", {})
            
            with kpi_container:
                # Active Hunts
                with ui.card().classes('col p-4 th-card border border-teal-500/20'):
                    with ui.row().classes('justify-between items-center w-full mb-1'):
                        ui.label('Active Hunts').classes('text-xs font-semibold text-slate-400 uppercase tracking-wider')
                        ui.icon('search', size='sm', color='teal-4')
                    ui.label(str(kpi.get("active_hunts", 0))).classes('text-3xl font-bold text-teal-400')
                    ui.label(f'{kpi.get("total_hunts", 0)} total campaigns').classes('text-xs text-slate-500 mt-1')

                # Sourced & Pipeline
                with ui.card().classes('col p-4 th-card border border-teal-500/20'):
                    with ui.row().classes('justify-between items-center w-full mb-1'):
                        ui.label('Sourced Candidates').classes('text-xs font-semibold text-slate-400 uppercase tracking-wider')
                        ui.icon('groups', size='sm', color='amber-4')
                    ui.label(str(kpi.get("total_sourced", 0))).classes('text-3xl font-bold text-amber-400')
                    ui.label(f'{kpi.get("interviewing_candidates", 0)} currently interviewing').classes('text-xs text-slate-500 mt-1')

                # Conversion Rate
                with ui.card().classes('col p-4 th-card border border-teal-500/20'):
                    with ui.row().classes('justify-between items-center w-full mb-1'):
                        ui.label('Funnel Conversion').classes('text-xs font-semibold text-slate-400 uppercase tracking-wider')
                        ui.icon('trending_up', size='sm', color='emerald-4')
                    ui.label(f'{kpi.get("conversion_rate", 0)}%').classes('text-3xl font-bold text-emerald-400')
                    ui.label(f'{kpi.get("hired_candidates", 0)} candidate hires').classes('text-xs text-slate-500 mt-1')

                # Avg Time-to-Fill
                with ui.card().classes('col p-4 th-card border border-teal-500/20'):
                    with ui.row().classes('justify-between items-center w-full mb-1'):
                        ui.label('Time-to-Fill').classes('text-xs font-semibold text-slate-400 uppercase tracking-wider')
                        ui.icon('schedule', size='sm', color='indigo-4')
                    ui.label(f'{kpi.get("avg_time_to_fill_days", 0)}d').classes('text-3xl font-bold text-indigo-400')
                    ui.label('Average days to position fill').classes('text-xs text-slate-500 mt-1')

                # AI Cost Savings
                with ui.card().classes('col p-4 th-card border border-teal-500/20'):
                    with ui.row().classes('justify-between items-center w-full mb-1'):
                        ui.label('AI Net Cost Saved').classes('text-xs font-semibold text-slate-400 uppercase tracking-wider')
                        ui.icon('savings', size='sm', color='cyan-4')
                    ui.label(f'${kpi.get("estimated_cost_saved", 0.0)}').classes('text-3xl font-bold text-cyan-400')
                    ui.label(f'{kpi.get("ai_actions", 0)} local AI operations').classes('text-xs text-slate-500 mt-1')

        def render_charts():
            charts_container.clear()
            funnel_data = state["data"].get("funnel", {})
            trends_data = state["data"].get("trends", {})
            velocity_data = state["data"].get("velocity", {})
            quality_data = state["data"].get("sourcing", {})
            ai_cost_data = state["data"].get("ai_cost", {})

            with charts_container:
                # Row 1: Funnel & Trends
                with ui.row().classes('w-full gap-6 no-wrap-md'):
                    # Chart 1: Talent Funnel Bar
                    with ui.card().classes('col-6 p-4 th-card border border-slate-800 w-full'):
                        ui.label('Talent Sourcing & Recruitment Funnel').classes('text-base font-semibold text-slate-200 mb-2')
                        
                        stages = [s["stage"] for s in funnel_data.get("stages", [])]
                        counts = [s["count"] for s in funnel_data.get("stages", [])]

                        ui.echart({
                            'backgroundColor': 'transparent',
                            'tooltip': {'trigger': 'axis', 'axisPointer': {'type': 'shadow'}},
                            'grid': {'top': '10%', 'left': '3%', 'right': '4%', 'bottom': '8%', 'containLabel': True},
                            'xAxis': {
                                'type': 'category',
                                'data': stages,
                                'axisLine': {'lineStyle': {'color': '#475569'}},
                                'axisLabel': {'color': '#94a3b8', 'fontSize': 11},
                            },
                            'yAxis': {
                                'type': 'value',
                                'axisLine': {'lineStyle': {'color': '#475569'}},
                                'splitLine': {'lineStyle': {'color': '#1e293b'}},
                                'axisLabel': {'color': '#94a3b8'},
                            },
                            'series': [{
                                'data': counts,
                                'type': 'bar',
                                'barWidth': '45%',
                                'itemStyle': {
                                    'color': {
                                        'type': 'linear',
                                        'x': 0, 'y': 0, 'x2': 0, 'y2': 1,
                                        'colorStops': [
                                            {'offset': 0, 'color': '#00d4aa'},
                                            {'offset': 1, 'color': '#0f766e'}
                                        ]
                                    },
                                    'borderRadius': [4, 4, 0, 0]
                                },
                                'label': {
                                    'show': True,
                                    'position': 'top',
                                    'color': '#2dd4bf',
                                    'fontWeight': 'bold',
                                }
                            }]
                        }).classes('h-72 w-full')

                    # Chart 2: Sourcing & Outreach Trends
                    with ui.card().classes('col-6 p-4 th-card border border-slate-800 w-full'):
                        ui.label('Sourcing & Outreach Activity Trends').classes('text-base font-semibold text-slate-200 mb-2')
                        
                        dates = trends_data.get("date_labels", [])
                        sourced_series = trends_data.get("candidates_sourced", [])
                        outreach_series = trends_data.get("outreach_sent", [])

                        ui.echart({
                            'backgroundColor': 'transparent',
                            'tooltip': {'trigger': 'axis'},
                            'legend': {
                                'data': ['Sourced Candidates', 'Outreach Sent'],
                                'textStyle': {'color': '#94a3b8'},
                                'top': '0%'
                            },
                            'grid': {'top': '15%', 'left': '3%', 'right': '4%', 'bottom': '8%', 'containLabel': True},
                            'xAxis': {
                                'type': 'category',
                                'data': dates,
                                'axisLine': {'lineStyle': {'color': '#475569'}},
                                'axisLabel': {'color': '#94a3b8', 'fontSize': 10},
                            },
                            'yAxis': {
                                'type': 'value',
                                'splitLine': {'lineStyle': {'color': '#1e293b'}},
                                'axisLabel': {'color': '#94a3b8'},
                            },
                            'series': [
                                {
                                    'name': 'Sourced Candidates',
                                    'type': 'line',
                                    'smooth': True,
                                    'data': sourced_series,
                                    'itemStyle': {'color': '#f59e0b'},
                                    'lineStyle': {'width': 3},
                                },
                                {
                                    'name': 'Outreach Sent',
                                    'type': 'line',
                                    'smooth': True,
                                    'data': outreach_series,
                                    'itemStyle': {'color': '#3b82f6'},
                                    'lineStyle': {'width': 3},
                                }
                            ]
                        }).classes('h-72 w-full')

                # Row 2: Time-to-Fill Velocity & Quality Match Score Distribution
                with ui.row().classes('w-full gap-6 no-wrap-md'):
                    # Chart 3: Time-to-Fill Velocity Breakdown
                    with ui.card().classes('col-6 p-4 th-card border border-slate-800 w-full'):
                        ui.label('Recruitment Velocity (Time-to-Fill Days per Hunt)').classes('text-base font-semibold text-slate-200 mb-2')
                        
                        hunts_vel = velocity_data.get("hunts_velocity", [])
                        h_titles = [(h.get("title") or "Untitled")[:22] + "..." if len((h.get("title") or "Untitled")) > 22 else (h.get("title") or "Untitled") for h in hunts_vel]
                        ttf_days = [h["time_to_fill_days"] for h in hunts_vel]

                        ui.echart({
                            'backgroundColor': 'transparent',
                            'tooltip': {'trigger': 'axis', 'axisPointer': {'type': 'shadow'}},
                            'grid': {'top': '10%', 'left': '3%', 'right': '8%', 'bottom': '8%', 'containLabel': True},
                            'xAxis': {
                                'type': 'value',
                                'splitLine': {'lineStyle': {'color': '#1e293b'}},
                                'axisLabel': {'color': '#94a3b8'},
                            },
                            'yAxis': {
                                'type': 'category',
                                'data': h_titles,
                                'axisLine': {'lineStyle': {'color': '#475569'}},
                                'axisLabel': {'color': '#94a3b8', 'fontSize': 11},
                            },
                            'series': [{
                                'data': ttf_days,
                                'type': 'bar',
                                'barWidth': '50%',
                                'itemStyle': {
                                    'color': '#818cf8',
                                    'borderRadius': [0, 4, 4, 0]
                                },
                                'label': {
                                    'show': True,
                                    'position': 'right',
                                    'color': '#a5b4fc',
                                    'formatter': '{c} days',
                                }
                            }]
                        }).classes('h-72 w-full')

                    # Chart 4: Candidate Match Score Distribution Donut
                    with ui.card().classes('col-6 p-4 th-card border border-slate-800 w-full'):
                        ui.label('Candidate Quality & Match Score Distribution').classes('text-base font-semibold text-slate-200 mb-2')
                        
                        scores = quality_data.get("score_distribution", {})
                        pie_data = [{'name': k, 'value': v} for k, v in scores.items()]

                        ui.echart({
                            'backgroundColor': 'transparent',
                            'tooltip': {'trigger': 'item', 'formatter': '{b}: {c} candidates ({d}%)'},
                            'legend': {
                                'orient': 'vertical',
                                'right': '5%',
                                'top': 'center',
                                'textStyle': {'color': '#94a3b8'}
                            },
                            'series': [{
                                'name': 'Match Score',
                                'type': 'pie',
                                'radius': ['45%', '75%'],
                                'center': ['35%', '50%'],
                                'avoidLabelOverlap': False,
                                'itemStyle': {
                                    'borderRadius': 6,
                                    'borderColor': '#0f172a',
                                    'borderWidth': 2
                                },
                                'label': {'show': False},
                                'data': pie_data,
                                'color': ['#10b981', '#3b82f6', '#f59e0b', '#ef4444']
                            }]
                        }).classes('h-72 w-full')

                # Row 3: AI Engine Cost & Token Usage Optimization Tracker
                with ui.row().classes('w-full gap-6'):
                    with ui.card().classes('w-full p-4 th-card border border-slate-800'):
                        with ui.row().classes('justify-between items-center w-full mb-2'):
                            ui.label('AI Engine Execution & Cost Optimization Tracker').classes('text-base font-semibold text-slate-200')
                            ui.chip('Local Edge LLM Enabled', icon='memory', color='teal').classes('text-xs')

                        with ui.row().classes('w-full items-center gap-8 py-2 px-4 bg-slate-900/60 rounded-lg border border-slate-800 mb-4'):
                            with ui.column().classes('gap-0'):
                                ui.label('Total AI Operations').classes('text-xs text-slate-400')
                                ui.label(str(ai_cost_data.get("total_operations", 0))).classes('text-xl font-bold text-slate-100')
                            with ui.column().classes('gap-0'):
                                ui.label('Executed on Local GGUF').classes('text-xs text-slate-400')
                                ui.label(f'{ai_cost_data.get("local_operations", 0)} ops').classes('text-xl font-bold text-teal-400')
                            with ui.column().classes('gap-0'):
                                ui.label('Cloud API Operations').classes('text-xs text-slate-400')
                                ui.label(f'{ai_cost_data.get("cloud_operations", 0)} ops').classes('text-xl font-bold text-amber-400')
                            with ui.column().classes('gap-0'):
                                ui.label('Actual Cloud API Cost').classes('text-xs text-slate-400')
                                ui.label(f'${ai_cost_data.get("actual_cloud_cost", 0.0)}').classes('text-xl font-bold text-slate-200')
                            with ui.column().classes('gap-0'):
                                ui.label('Net Savings vs Full Cloud').classes('text-xs text-slate-400')
                                ui.label(f'${ai_cost_data.get("total_cost_saved", 0.0)}').classes('text-xl font-bold text-emerald-400')

                        op_breakdown = ai_cost_data.get("operation_breakdown", {})
                        op_names = list(op_breakdown.keys())
                        op_vals = list(op_breakdown.values())

                        ui.echart({
                            'backgroundColor': 'transparent',
                            'tooltip': {'trigger': 'axis', 'axisPointer': {'type': 'shadow'}},
                            'grid': {'top': '10%', 'left': '3%', 'right': '4%', 'bottom': '12%', 'containLabel': True},
                            'xAxis': {
                                'type': 'category',
                                'data': op_names,
                                'axisLine': {'lineStyle': {'color': '#475569'}},
                                'axisLabel': {'color': '#94a3b8', 'fontSize': 10, 'interval': 0, 'rotate': 15},
                            },
                            'yAxis': {
                                'type': 'value',
                                'axisLine': {'lineStyle': {'color': '#475569'}},
                                'splitLine': {'lineStyle': {'color': '#1e293b'}},
                                'axisLabel': {'color': '#94a3b8'},
                            },
                            'series': [{
                                'name': 'AI Operations',
                                'type': 'bar',
                                'barWidth': '40%',
                                'itemStyle': {
                                    'color': '#06b6d4',
                                    'borderRadius': [4, 4, 0, 0]
                                },
                                'label': {'show': True, 'position': 'top', 'color': '#22d3ee'}
                            }]
                        }).classes('h-64 w-full')

        def render_tables():
            tables_container.clear()
            velocity_data = state["data"].get("velocity", {})
            outreach_data = state["data"].get("outreach", {})

            with tables_container:
                # Campaign Velocity Table
                with ui.card().classes('w-full p-4 th-card border border-slate-800'):
                    ui.label('Campaign Performance & Velocity Breakdown').classes('text-base font-semibold text-slate-200 mb-3')
                    
                    columns = [
                        {'name': 'title', 'label': 'Campaign Title', 'field': 'title', 'align': 'left', 'sortable': True},
                        {'name': 'target_role', 'label': 'Target Role', 'field': 'target_role', 'align': 'left'},
                        {'name': 'status', 'label': 'Status', 'field': 'status', 'align': 'center'},
                        {'name': 'total_candidates', 'label': 'Total Sourced', 'field': 'total_candidates', 'align': 'right', 'sortable': True},
                        {'name': 'hired_count', 'label': 'Hired', 'field': 'hired_count', 'align': 'right', 'sortable': True},
                        {'name': 'days_open', 'label': 'Days Open', 'field': 'days_open', 'align': 'right', 'sortable': True},
                        {'name': 'time_to_fill_days', 'label': 'Time-to-Fill (Days)', 'field': 'time_to_fill_days', 'align': 'right', 'sortable': True},
                    ]

                    rows = velocity_data.get("hunts_velocity", [])

                    ui.table(columns=columns, rows=rows, row_key='hunt_id').classes('w-full bg-transparent text-slate-200').props('flat')

        def update_dashboard(selected_hunt=None, days=None):
            if selected_hunt is not None:
                state["selected_hunt_id"] = selected_hunt
            if days is not None:
                state["time_range_days"] = days

            fetch_data()
            render_kpi_cards()
            render_charts()
            render_tables()
            ui.notify("Dashboard metrics updated", type='info', color='teal')

        def handle_export_pdf():
            pdf_bytes = generate_analytics_pdf(state["data"])
            ui.download(pdf_bytes, filename=f"TalentHunt_Analytics_{datetime.now(timezone.utc).strftime('%Y%m%d')}.pdf")
            ui.notify("Executive Analytics PDF generated and downloaded!", type='positive')

        def handle_export_csv():
            csv_str = generate_analytics_csv(state["data"])
            csv_bytes = csv_str.encode("utf-8")
            ui.download(csv_bytes, filename=f"TalentHunt_Metrics_{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv")
            ui.notify("Analytics CSV file generated and downloaded!", type='positive')

        # Initial Render
        render_kpi_cards()
        render_charts()
        render_tables()


def analytics_page():
    """Page wrapper with 3-panel shell layout."""
    create_layout(render_analytics)
