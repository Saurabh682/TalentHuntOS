"""Create and resolve bounded local report artifacts."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import select

from app.analytics.models import ReportArtifact
from app.config.settings import DATA_DIR

ReportFormat = Literal["csv", "xlsx", "pdf"]

REPORTS_DIR = DATA_DIR / "reports"
MAX_REPORT_BYTES = 25 * 1024 * 1024
FORMAT_DETAILS: dict[str, tuple[str, str]] = {
    "csv": ("text/csv; charset=utf-8", "csv"),
    "xlsx": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xlsx",
    ),
    "pdf": ("application/pdf", "pdf"),
}


def _json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _loads(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}


def _safe_root() -> Path:
    root = REPORTS_DIR.resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def resolve_report_path(relative_path: str) -> Path:
    """Resolve only artifact-owned files beneath the configured reports directory."""
    if not relative_path or Path(relative_path).is_absolute():
        raise ValueError("Report artifact path is invalid.")
    root = _safe_root()
    candidate = (root / relative_path).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("Report artifact path escapes the reports directory.")
    return candidate


def _public_artifact(row: ReportArtifact) -> dict[str, Any]:
    return {
        "id": row.id,
        "report_type": row.report_type,
        "format": row.format,
        "title": row.title,
        "file_name": row.file_name,
        "media_type": row.media_type,
        "size_bytes": row.size_bytes,
        "sha256": row.sha256,
        "hunt_id": row.hunt_id,
        "hunt_title": row.hunt_title,
        "days": row.days,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "download_url": f"/api/reports/{row.id}",
        "provenance": _loads(row.provenance_json),
    }


def create_analytics_report(
    *,
    report_format: ReportFormat,
    hunt_id: int | None,
    days: int,
    actor_type: str,
    session_id: str | None,
) -> dict[str, Any]:
    """Create one canonical analytics snapshot in a fixed private output directory."""
    from app.analytics.reports import (
        generate_analytics_csv,
        generate_analytics_excel,
        generate_analytics_pdf,
    )
    from app.analytics.service import get_all_analytics_data
    from app.hunts.models import TalentHunt
    from app.infrastructure import db as dbinfra

    normalized_format = str(report_format).strip().lower()
    if normalized_format not in FORMAT_DETAILS:
        raise ValueError("Report format must be csv, xlsx, or pdf.")
    if not 1 <= int(days) <= 365:
        raise ValueError("Report trend window must be between 1 and 365 days.")

    generated_at = datetime.now(timezone.utc)
    with dbinfra.SessionFactory() as db:
        hunt = db.get(TalentHunt, int(hunt_id)) if hunt_id is not None else None
        if hunt_id is not None and not hunt:
            raise ValueError("Talent Hunt not found.")
        hunt_title = hunt.title if hunt else None
        scope_label = hunt_title or "All Talent Hunts"
        metrics = get_all_analytics_data(db, hunt_id=hunt_id, days=int(days))

    renderers = {
        "csv": lambda: generate_analytics_csv(
            metrics, generated_at=generated_at, scope_label=scope_label
        ).encode("utf-8-sig"),
        "xlsx": lambda: generate_analytics_excel(
            metrics, generated_at=generated_at, scope_label=scope_label
        ),
        "pdf": lambda: generate_analytics_pdf(
            metrics, generated_at=generated_at, scope_label=scope_label
        ),
    }
    content = renderers[normalized_format]()
    if not content:
        raise RuntimeError("Report renderer produced an empty artifact.")
    if len(content) > MAX_REPORT_BYTES:
        raise RuntimeError("Report exceeds the 25 MB local artifact limit.")

    artifact_id = uuid.uuid4().hex[:20]
    media_type, extension = FORMAT_DETAILS[normalized_format]
    stamp = generated_at.strftime("%Y%m%dT%H%M%SZ")
    scope_slug = f"hunt-{hunt_id}" if hunt_id is not None else "all-hunts"
    file_name = f"TalentHunt_Analytics_{scope_slug}_{stamp}_{artifact_id[:6]}.{extension}"
    target = resolve_report_path(file_name)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(target)

    provenance = {
        "source_of_truth": "canonical TalentHunt database records",
        "service": "app.analytics.service.get_all_analytics_data",
        "renderer": (
            "app.analytics.reports.generate_analytics_excel"
            if normalized_format == "xlsx"
            else f"app.analytics.reports.generate_analytics_{normalized_format}"
        ),
        "tables": [
            "talent_hunts",
            "candidates",
            "hunt_candidates",
            "hunt_stages",
            "communications",
            "outreach_sequences",
            "outreach_enrollments",
            "hunt_activities",
        ],
        "filters": {"hunt_id": hunt_id, "days": int(days)},
        "snapshot_at": generated_at.isoformat(),
        "limitations": [
            "Provider token and billing telemetry is not persisted; unavailable cost fields remain zero.",
            "Average time to fill is based only on recorded hired transitions.",
        ],
    }
    row = ReportArtifact(
        id=artifact_id,
        report_type="analytics",
        format=normalized_format,
        title=f"Analytics - {scope_label}",
        file_name=file_name,
        relative_path=file_name,
        media_type=media_type,
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        hunt_id=hunt_id,
        hunt_title=hunt_title,
        days=int(days),
        actor_type=actor_type,
        session_id=session_id,
        provenance_json=_json(provenance),
        created_at=generated_at,
    )
    try:
        with dbinfra.SessionFactory() as db:
            db.add(row)
            db.commit()
            db.refresh(row)
            return _public_artifact(row)
    except Exception:
        target.unlink(missing_ok=True)
        raise


def get_report_artifact(artifact_id: str) -> dict[str, Any]:
    from app.infrastructure import db as dbinfra

    normalized = (artifact_id or "").strip().lower()
    if len(normalized) != 20 or not normalized.isalnum():
        raise ValueError("Report artifact ID is invalid.")
    with dbinfra.SessionFactory() as db:
        row = db.get(ReportArtifact, normalized)
        if not row:
            raise ValueError("Report artifact not found.")
        result = _public_artifact(row)
        path = resolve_report_path(row.relative_path)
        result["available"] = path.is_file()
        return result


def get_report_download(artifact_id: str) -> tuple[Path, dict[str, Any]]:
    from app.infrastructure import db as dbinfra

    normalized = (artifact_id or "").strip().lower()
    if len(normalized) != 20 or not normalized.isalnum():
        raise ValueError("Report artifact ID is invalid.")
    with dbinfra.SessionFactory() as db:
        row = db.get(ReportArtifact, normalized)
        if not row:
            raise ValueError("Report artifact not found.")
        path = resolve_report_path(row.relative_path)
        if not path.is_file():
            raise FileNotFoundError("Report file is no longer available.")
        if path.stat().st_size != row.size_bytes:
            raise RuntimeError("Report file size no longer matches its artifact record.")
        if hashlib.sha256(path.read_bytes()).hexdigest() != row.sha256:
            raise RuntimeError("Report file checksum no longer matches its artifact record.")
        return path, _public_artifact(row)


def list_report_artifacts(
    *, report_format: str | None = None, hunt_id: int | None = None, limit: int = 20
) -> list[dict[str, Any]]:
    from app.infrastructure import db as dbinfra

    with dbinfra.SessionFactory() as db:
        stmt = select(ReportArtifact).order_by(ReportArtifact.created_at.desc())
        if report_format:
            stmt = stmt.where(ReportArtifact.format == report_format)
        if hunt_id is not None:
            stmt = stmt.where(ReportArtifact.hunt_id == int(hunt_id))
        rows = list(db.scalars(stmt.limit(max(1, min(int(limit), 100)))).all())
        results = []
        for row in rows:
            item = _public_artifact(row)
            item["available"] = resolve_report_path(row.relative_path).is_file()
            results.append(item)
        return results
