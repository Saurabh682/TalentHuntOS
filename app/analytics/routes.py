"""Authenticated download route for durable local reports."""

from __future__ import annotations

from fastapi import HTTPException
from fastapi.responses import FileResponse

from app.analytics.artifacts import get_report_download


def download_report_artifact(artifact_id: str) -> FileResponse:
    try:
        path, artifact = get_report_download(artifact_id)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return FileResponse(
        path,
        media_type=artifact["media_type"],
        filename=artifact["file_name"],
        headers={"Cache-Control": "private, no-store"},
    )


def register_report_routes(app) -> None:
    app.add_api_route(
        "/api/reports/{artifact_id}",
        download_report_artifact,
        methods=["GET"],
        name="download_report_artifact",
    )
