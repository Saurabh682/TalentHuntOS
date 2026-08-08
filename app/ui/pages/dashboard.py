"""Dashboard page for TalentHunt OS — Modern Ocean design."""

from nicegui import ui
from app.ui.layout import create_layout
from app.infrastructure.db import SessionFactory, init_db
from app.analytics.service import get_kpi_summary, get_hunt_funnel_data, get_sourcing_quality_metrics


def _fmt_inr(amount: float) -> str:
    try:
        return f"₹{amount:,.1f}K" if amount >= 1000 else f"₹{amount:,.0f}"
    except Exception:
        return "₹0"


def render_dashboard():
    """Render the main overview dashboard matching the Modern HTML UI."""
    init_db()
    kpi = {}
    funnel = {}
    sourcing = {}
    try:
        with SessionFactory() as db:
            kpi = get_kpi_summary(db) or {}
            funnel = get_hunt_funnel_data(db) or {}
            sourcing = get_sourcing_quality_metrics(db) or {}
    except Exception:
        pass

    active_hunts = kpi.get("active_hunts", 0)
    sourced = kpi.get("total_sourced", 0)
    conversion = kpi.get("conversion_rate", 0)
    ai_actions = kpi.get("ai_actions", 0)
    cost_saved = kpi.get("estimated_cost_saved", 0)
    ttf = kpi.get("avg_time_to_fill_days", 0)

    stage_counts = funnel.get("stage_counts") or funnel.get("stages") or {}
    if isinstance(stage_counts, list):
        # Convert list of dicts if needed
        stage_map = {s.get("name", s.get("stage", "")): s.get("count", 0) for s in stage_counts}
    else:
        stage_map = dict(stage_counts)

    funnel_stages = [
        ("Sourced", stage_map.get("Sourced", sourced)),
        ("Contacted", stage_map.get("Contacted", 0)),
        ("Screening", stage_map.get("Screening", 0)),
        ("Interview", stage_map.get("Interview", 0)),
        ("Offered", stage_map.get("Offer", stage_map.get("Offered", 0))),
        ("Hired", stage_map.get("Hired", kpi.get("hired_candidates", 0))),
    ]
    max_count = max([c for _, c in funnel_stages] + [1])

    with ui.column().classes('w-full gap-0'):
        # Top header
        with ui.row().classes('w-full justify-between items-center gap-5 mb-[22px]'):
            with ui.column().classes('gap-0'):
                ui.label('Talent intelligence').classes('th-ey')
                ui.label('Welcome back, Recruiter').classes('th-title')
                ui.label("Here's what's happening with your recruitment engine today.").classes('th-muted')
            ui.button('＋ New Talent Hunt', on_click=lambda: ui.navigate.to('/hunts')).classes('th-primary-btn')

        # Stat cards — 5 columns
        with ui.row().classes('w-full gap-[13px] no-wrap'):
            stats = [
                ('ACTIVE HUNTS', str(active_hunts), 'Campaigns running'),
                ('CANDIDATES SOURCED', str(sourced), 'Talent pool size'),
                ('PIPELINE CONVERSION', f'{conversion}%', 'Sourced → Hired'),
                ('AI ACTIONS TODAY', str(ai_actions), 'Auto-pilot & Copilot'),
                ('NET COST SAVED', _fmt_inr(float(cost_saved) * 1000 if cost_saved < 100 else cost_saved), 'vs cloud AI spend'),
            ]
            for label, num, sub in stats:
                with ui.element('div').classes('th-card col p-4'):
                    ui.label(label).classes('th-label')
                    ui.label(num).classes('th-num')
                    ui.label(sub).classes('th-up')

        # Two-column lower section
        with ui.row().classes('w-full gap-[13px] mt-[13px] no-wrap items-stretch'):
            # Funnel panel (wide)
            with ui.element('div').classes('th-panel col grow p-4'):
                with ui.row().classes('w-full justify-between mb-[14px]'):
                    ui.label('Talent Sourcing & Recruitment Funnel').classes('text-[13px] font-semibold text-[#edf5f7]')
                    ui.label('Last 30 Days').classes('th-muted')

                with ui.element('div').classes('th-funnel w-full'):
                    for name, count in funnel_stages:
                        pct = int((count / max_count) * 100) if max_count else 0
                        with ui.element('div').classes('th-funnel-stage'):
                            ui.label(name).classes('text-[11px] font-semibold text-[#edf5f7]')
                            ui.label(str(count)).classes('text-[19px] font-bold text-[#edf5f7] my-[7px]')
                            with ui.element('div').classes('th-bar'):
                                ui.element('i').classes('th-bar-fill').style(f'width:{pct}%')

                ui.element('div').classes('th-chart-spark')

            # Right column: donut + insights
            with ui.column().classes('w-[320px] shrink-0 gap-[13px]'):
                with ui.element('div').classes('th-panel p-4'):
                    with ui.row().classes('w-full justify-between mb-[14px]'):
                        ui.label('Sourcing & Outreach').classes('text-[13px] font-semibold text-[#edf5f7]')
                        ui.label('This Week').classes('th-muted')
                    ui.element('div').classes('th-donut').props(f'data-center="{sourced}"')
                    ui.label('● Sourced　 ● Contacted　 ● Interview').classes('th-muted text-center w-full')

                with ui.element('div').classes('th-panel p-4'):
                    with ui.row().classes('w-full justify-between mb-[14px]'):
                        ui.label('AI Insights').classes('text-[13px] font-semibold text-[#edf5f7]')
                        ui.label('Live').classes('th-muted')

                    channels = sourcing.get("channels_breakdown") if isinstance(sourcing, dict) else None
                    if isinstance(channels, dict) and channels:
                        top_source = max(channels.items(), key=lambda x: x[1])[0]
                    else:
                        top_source = "Internal DB"
                    insights = [
                        ('Top performing source', f'{top_source} is driving quality candidates into active hunts.'),
                        ('Time to fill', f'Average time to fill is {ttf or "—"} days.'),
                        ('Cost efficiency', f'Estimated cloud AI spend avoided: {_fmt_inr(float(cost_saved) * 1000 if cost_saved < 100 else cost_saved)}.'),
                    ]
                    for title, desc in insights:
                        with ui.element('div').classes('th-insight'):
                            ui.label(title).classes('text-[12px] font-semibold text-[#edf5f7]')
                            ui.label(desc).classes('th-muted mt-1')


def dashboard_page():
    create_layout(render_dashboard)
