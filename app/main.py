"""TalentHunt OS Main Entry Point."""

from nicegui import app as nicegui_app
from nicegui import ui

from app.config.preferences import load_app_preferences
from app.config.settings import DATA_DIR, settings
from app.infrastructure.auth import storage_secret
from app.infrastructure.auth_routes import register_auth
from app.infrastructure.logging_setup import configure_logging

load_app_preferences()
configure_logging()
register_auth(nicegui_app)

# Import voice audio bridge to register WebSocket endpoint at /ws/audio
import app.voice.audio_bridge  # noqa: F401
from app.analytics.routes import register_report_routes
from app.ui.pages.analytics import analytics_page
from app.ui.pages.candidate_detail import candidate_detail_page
from app.ui.pages.candidates import candidates_page
from app.ui.pages.communications import communications_page
from app.ui.pages.dashboard import dashboard_page
from app.ui.pages.discoveries import discoveries_page
from app.ui.pages.hunts import hunts_page
from app.ui.pages.intake import intake_page
from app.ui.pages.pipeline import pipeline_page
from app.ui.pages.playbook import playbook_page
from app.ui.pages.settings import settings_page
from app.voice.tts_api import register_tts_routes

register_tts_routes()
register_report_routes(nicegui_app)

PROFILE_SNAPSHOT_DIR = DATA_DIR / "profile_snapshots"
PROFILE_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
nicegui_app.add_static_files("/profile-snapshots", str(PROFILE_SNAPSHOT_DIR))


# Page registration
@ui.page("/")
def index():
    dashboard_page()


@ui.page("/hunts")
def hunts_view():
    hunts_page()


@ui.page("/hunts/{hunt_id}/pipeline")
def hunt_pipeline_view(hunt_id: int):
    pipeline_page(hunt_id)


@ui.page("/pipeline")
def pipeline_view():
    pipeline_page()


@ui.page("/playbook")
def playbook_view():
    playbook_page()


@ui.page("/candidates")
def candidates_view():
    candidates_page()


@ui.page("/discoveries")
def discoveries_view():
    discoveries_page()


@ui.page("/candidates/{candidate_id}")
def candidate_detail_view(candidate_id: int):
    candidate_detail_page(candidate_id)


@ui.page("/intake/{token}")
def intake_view(token: str):
    """Public candidate intake form (tokenized; no app chrome)."""
    intake_page(token)


@ui.page("/communications")
def communications_view():
    communications_page()


@ui.page("/analytics")
def analytics_view():
    analytics_page()


@ui.page("/settings")
def settings_view():
    settings_page()


if __name__ in {"__main__", "__mp_main__"}:
    from app.infrastructure.db import init_db

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    init_db()
    from app.jobs.runner import recover_interrupted_workflows

    recovered_jobs = recover_interrupted_workflows()
    if recovered_jobs:
        print(f"Recovered {recovered_jobs} interrupted background job(s).")

    from app.ai.embedded_jobs import schedule_embedded_ai_autostart
    from app.ai.local_server import local_server_manager

    nicegui_app.on_startup(schedule_embedded_ai_autostart)
    nicegui_app.on_shutdown(local_server_manager.stop)
    print(
        f"Starting {settings.app_name} v{settings.app_version} on http://{settings.host}:{settings.port}"
    )
    ui.run(
        host=settings.host,
        port=settings.port,
        title=settings.app_name,
        dark=True,
        reload=False,
        storage_secret=storage_secret(),
    )
