"""Analytics and Intelligence package for TalentHunt OS."""

from app.analytics.service import (
    get_kpi_summary,
    get_hunt_funnel_data,
    get_time_to_fill_metrics,
    get_sourcing_quality_metrics,
    get_outreach_analytics,
    get_ai_cost_tracker,
    get_trend_analytics,
    get_all_analytics_data,
)
from app.analytics.reports import (
    generate_analytics_csv,
    generate_analytics_pdf,
    generate_analytics_excel,
)

__all__ = [
    "get_kpi_summary",
    "get_hunt_funnel_data",
    "get_time_to_fill_metrics",
    "get_sourcing_quality_metrics",
    "get_outreach_analytics",
    "get_ai_cost_tracker",
    "get_trend_analytics",
    "get_all_analytics_data",
    "generate_analytics_csv",
    "generate_analytics_pdf",
    "generate_analytics_excel",
]
