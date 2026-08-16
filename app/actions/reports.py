"""Registered local report actions shared by Copilot and Analytics UI."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.actions.context import ActionContext
from app.actions.registry import register_action

ReportFormat = Literal["csv", "xlsx", "pdf"]


class ReportCreateInput(BaseModel):
    format: ReportFormat = "pdf"
    hunt_id: int | None = Field(default=None, gt=0)
    days: int = Field(default=30, ge=1, le=365)


class ReportListInput(BaseModel):
    format: ReportFormat | None = None
    hunt_id: int | None = Field(default=None, gt=0)
    limit: int = Field(default=20, ge=1, le=100)


class ReportGetInput(BaseModel):
    artifact_id: str = Field(min_length=20, max_length=20)

    @field_validator("artifact_id")
    @classmethod
    def valid_artifact_id(cls, value: str) -> str:
        normalized = value.strip().lower()
        if len(normalized) != 20 or not normalized.isalnum():
            raise ValueError("artifact_id must be a 20-character alphanumeric ID")
        return normalized


def _create_resources(data: ReportCreateInput, ctx: ActionContext) -> list[str]:
    resources = ["reports:local-output"]
    if data.hunt_id is not None:
        resources.append(f"hunt:{data.hunt_id}")
    return resources


@register_action(
    "reports.analytics.create",
    description=(
        "Create a local CSV, real XLSX workbook, or PDF analytics artifact from canonical "
        "TalentHunt database metrics. Returns an authenticated download link and provenance."
    ),
    input_model=ReportCreateInput,
    resource_resolver=_create_resources,
    classification="system",
    risk_level="R1",
    required_scopes=("read", "write"),
    copilot_enabled=True,
    copilot_tool_name="create_analytics_report",
)
def create_analytics_report_action(
    data: ReportCreateInput, ctx: ActionContext
) -> dict[str, object]:
    from app.analytics.artifacts import create_analytics_report

    artifact = create_analytics_report(
        report_format=data.format,
        hunt_id=data.hunt_id,
        days=data.days,
        actor_type="copilot" if ctx.actor_type == "agent" else ctx.actor_type,
        session_id=ctx.session_id,
    )
    return {
        "status": "success",
        "message": f"{data.format.upper()} analytics report created locally.",
        "artifact": artifact,
    }


@register_action(
    "reports.list",
    description=(
        "List bounded local report artifact metadata and authenticated download links. "
        "Internal filesystem paths are never returned."
    ),
    input_model=ReportListInput,
    classification="query",
    risk_level="R0",
    required_scopes=("read",),
    copilot_enabled=True,
    copilot_tool_name="list_report_artifacts",
)
def list_report_artifacts_action(data: ReportListInput, ctx: ActionContext) -> dict[str, object]:
    from app.analytics.artifacts import list_report_artifacts

    artifacts = list_report_artifacts(
        report_format=data.format,
        hunt_id=data.hunt_id,
        limit=data.limit,
    )
    return {"status": "success", "count": len(artifacts), "artifacts": artifacts}


@register_action(
    "reports.get",
    description=(
        "Get one local report artifact's safe metadata, availability, checksum, provenance, "
        "and authenticated download link."
    ),
    input_model=ReportGetInput,
    classification="query",
    risk_level="R0",
    required_scopes=("read",),
    copilot_enabled=True,
    copilot_tool_name="get_report_artifact",
)
def get_report_artifact_action(data: ReportGetInput, ctx: ActionContext) -> dict[str, object]:
    from app.analytics.artifacts import get_report_artifact

    return {"status": "success", "artifact": get_report_artifact(data.artifact_id)}
