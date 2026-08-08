"""TalentHunt OS Main Entry Point."""

from nicegui import ui
from app.config.settings import settings
from app.ui.pages.dashboard import dashboard_page
from app.ui.pages.settings import settings_page
from app.ui.pages.hunts import hunts_page
from app.ui.pages.pipeline import pipeline_page

from app.ui.pages.candidates import candidates_page
from app.ui.pages.candidate_detail import candidate_detail_page
from app.ui.pages.communications import communications_page
from app.ui.pages.analytics import analytics_page

# Import voice audio bridge to register WebSocket endpoint at /ws/audio
import app.voice.audio_bridge  # noqa: F401

# Page registration
@ui.page('/')
def index():
    dashboard_page()

@ui.page('/hunts')
def hunts_view():
    hunts_page()

@ui.page('/hunts/{hunt_id}/pipeline')
def hunt_pipeline_view(hunt_id: int):
    pipeline_page(hunt_id)

@ui.page('/pipeline')
def pipeline_view():
    pipeline_page()

@ui.page('/candidates')
def candidates_view():
    candidates_page()

@ui.page('/candidates/{candidate_id}')
def candidate_detail_view(candidate_id: int):
    candidate_detail_page(candidate_id)

@ui.page('/communications')
def communications_view():
    communications_page()

@ui.page('/analytics')
def analytics_view():
    analytics_page()

@ui.page('/settings')
def settings_view():
    settings_page()

if __name__ in {"__main__", "__mp_main__"}:
    from app.infrastructure.db import init_db
    init_db()
    print(f"Starting {settings.app_name} v{settings.app_version} on http://{settings.host}:{settings.port}")
    ui.run(
        host=settings.host,
        port=settings.port,
        title=settings.app_name,
        dark=True,
        reload=False,
        storage_secret="talenthunt-os-local-storage",
    )
