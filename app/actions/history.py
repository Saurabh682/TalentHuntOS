"""Record, inspect, and reverse durable application actions."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.actions.models import ActionHistory

DEFAULT_UNDO_DAYS = 7


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def record_action(
    db: Session,
    *,
    action_type: str,
    summary: str,
    payload: dict[str, Any] | None = None,
    undo_payload: dict[str, Any] | None = None,
    actor_type: str = "copilot",
    session_id: str | None = None,
    undo_days: int = DEFAULT_UNDO_DAYS,
) -> ActionHistory:
    now = _utcnow()
    item = ActionHistory(
        action_type=action_type,
        summary=summary,
        actor_type=actor_type,
        session_id=session_id,
        payload_json=json.dumps(payload or {}),
        undo_payload_json=json.dumps(undo_payload) if undo_payload is not None else None,
        undo_expires_at=now + timedelta(days=max(1, undo_days))
        if undo_payload is not None
        else None,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def list_recent_actions(
    db: Session,
    *,
    days: int = DEFAULT_UNDO_DAYS,
    limit: int = 50,
    session_id: str | None = None,
) -> list[ActionHistory]:
    cutoff = _utcnow() - timedelta(days=max(1, days))
    stmt = select(ActionHistory).where(ActionHistory.created_at >= cutoff)
    if session_id is not None:
        stmt = stmt.where(ActionHistory.session_id == session_id)
    stmt = stmt.order_by(ActionHistory.created_at.desc()).limit(max(1, min(limit, 200)))
    return list(db.scalars(stmt).all())


def is_undoable(item: ActionHistory) -> bool:
    if item.status != "completed" or not item.undo_payload_json or not item.undo_expires_at:
        return False
    expires = item.undo_expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return expires >= _utcnow()


def get_undoable_action(db: Session, action_id: int | str = "latest") -> ActionHistory:
    stmt = select(ActionHistory).order_by(ActionHistory.created_at.desc())
    if str(action_id).lower() != "latest":
        stmt = stmt.where(ActionHistory.id == int(action_id))
    candidates = list(db.scalars(stmt.limit(200)).all())
    item = next((entry for entry in candidates if is_undoable(entry)), None)
    if not item:
        raise ValueError("No matching undoable action was found in the seven-day history.")
    return item


def action_resource_keys(db: Session, item: ActionHistory) -> list[str]:
    """Resolve canonical resources affected by undoing one history entry."""
    payload = json.loads(item.payload_json or "{}")
    undo_payload = json.loads(item.undo_payload_json or "{}")
    keys: set[str] = set()

    candidate_id = payload.get("candidate_id") or (undo_payload.get("candidate_state") or {}).get(
        "id"
    )
    if candidate_id:
        keys.add(f"candidate:{int(candidate_id)}")
    for value in payload.get("candidate_ids", []):
        keys.add(f"candidate:{int(value)}")

    hunt_id = payload.get("hunt_id") or undo_payload.get("hunt_id")
    match_id = payload.get("match_id") or undo_payload.get("match_id")
    hunt_candidate_id = payload.get("hunt_candidate_id") or undo_payload.get("hunt_candidate_id")
    if match_id:
        keys.add(f"discovery-match:{int(match_id)}")
        if not hunt_id:
            from app.candidates.models import DiscoveryHuntMatch

            match = db.get(DiscoveryHuntMatch, int(match_id))
            hunt_id = match.hunt_id if match else None
    if hunt_candidate_id:
        keys.add(f"hunt-candidate:{int(hunt_candidate_id)}")
        if not hunt_id:
            from app.hunts.models import HuntCandidate

            enrollment = db.get(HuntCandidate, int(hunt_candidate_id))
            hunt_id = enrollment.hunt_id if enrollment else None
    if hunt_id:
        keys.add(f"hunt:{int(hunt_id)}")
    request_id = payload.get("request_id") or undo_payload.get("request_id")
    submission_id = payload.get("submission_id") or undo_payload.get("submission_id")
    playbook_entry_id = payload.get("playbook_entry_id") or undo_payload.get("playbook_entry_id")
    if request_id:
        keys.add(f"intake-request:{int(request_id)}")
    if submission_id:
        keys.add(f"intake-submission:{int(submission_id)}")
    if playbook_entry_id:
        keys.add(f"playbook-entry:{int(playbook_entry_id)}")
    if item.action_type == "disconnect_site" and payload.get("platform"):
        keys.add(f"connection:{str(payload['platform']).lower()}")
    if item.action_type == "archive_common_pool":
        keys.add("discoveries:common-pool")
    if item.action_type == "configure_embedded_ai":
        keys.add("ai-runtime:embedded")
    communication_id = payload.get("communication_id") or undo_payload.get("communication_id")
    thread_id = payload.get("thread_id") or undo_payload.get("created_thread_id")
    template_id = (
        payload.get("template_id")
        or undo_payload.get("template_id")
        or (undo_payload.get("template") or {}).get("id")
    )
    sequence_id = payload.get("sequence_id") or undo_payload.get("sequence_id")
    step_id = payload.get("step_id") or undo_payload.get("step_id")
    enrollment_id = payload.get("enrollment_id") or undo_payload.get("enrollment_id")
    if communication_id:
        keys.add(f"communication:{int(communication_id)}")
    if thread_id:
        keys.add(f"communication-thread:{int(thread_id)}")
    if template_id:
        keys.add(f"message-template:{int(template_id)}")
    if sequence_id:
        keys.add(f"outreach-sequence:{int(sequence_id)}")
    if step_id:
        keys.add(f"outreach-step:{int(step_id)}")
    if enrollment_id:
        keys.add(f"outreach-enrollment:{int(enrollment_id)}")
    return sorted(keys)


def action_target(db: Session, item: ActionHistory) -> dict[str, str] | None:
    """Return a safe in-app destination for the action's primary affected record."""
    payload = json.loads(item.payload_json or "{}")
    undo_payload = json.loads(item.undo_payload_json or "{}")
    candidate_id = payload.get("candidate_id") or (undo_payload.get("candidate_state") or {}).get(
        "id"
    )
    if candidate_id:
        return {"url": f"/candidates/{int(candidate_id)}", "label": "Open candidate"}
    if item.action_type == "archive_candidates":
        return {"url": "/candidates", "label": "Open candidates"}
    if item.action_type == "archive_hunt":
        return {"url": "/hunts", "label": "Open Hunts"}
    if item.action_type == "archive_common_pool":
        return {"url": "/discoveries", "label": "Open Discoveries"}

    hunt_id = payload.get("hunt_id") or undo_payload.get("hunt_id")
    match_id = payload.get("match_id") or undo_payload.get("match_id")
    hunt_candidate_id = payload.get("hunt_candidate_id") or undo_payload.get("hunt_candidate_id")
    if match_id and not hunt_id:
        from app.candidates.models import DiscoveryHuntMatch

        match = db.get(DiscoveryHuntMatch, int(match_id))
        hunt_id = match.hunt_id if match else None
    if hunt_candidate_id and not hunt_id:
        from app.hunts.models import HuntCandidate

        enrollment = db.get(HuntCandidate, int(hunt_candidate_id))
        hunt_id = enrollment.hunt_id if enrollment else None
    if item.action_type in {"approve_discovered_profile", "reject_discovered_profile"}:
        return {"url": "/discoveries", "label": "Open Discoveries"}
    if hunt_id:
        return {"url": f"/hunts/{int(hunt_id)}/pipeline", "label": "Open pipeline"}
    if item.action_type == "disconnect_site":
        return {"url": "/settings", "label": "Open settings"}
    if item.action_type == "configure_embedded_ai":
        return {"url": "/settings", "label": "Open settings"}
    if item.action_type.startswith(
        ("create_communication_", "set_communication_")
    ) or item.action_type in {
        "send_communication_email",
        "create_message_template",
        "update_message_template",
        "set_message_template_active",
        "create_outreach_sequence",
        "update_outreach_sequence",
        "set_outreach_sequence_active",
        "add_outreach_step",
        "enroll_outreach_candidate",
        "set_outreach_enrollment_status",
    }:
        return {"url": "/communications", "label": "Open communications"}
    return None


def undo_action(db: Session, action_id: int | str = "latest") -> ActionHistory:
    item = get_undoable_action(db, action_id)

    payload = json.loads(item.undo_payload_json or "{}")
    if item.action_type == "archive_candidates":
        from app.candidates.models import Candidate

        previous = payload.get("previous_statuses", {})
        for candidate_id, status in previous.items():
            candidate = db.get(Candidate, int(candidate_id))
            if candidate:
                candidate.status = status
    elif item.action_type == "archive_common_pool":
        from app.candidates.discovery import ARCHIVED_STATUS
        from app.candidates.models import DiscoveredProfile, DiscoveryHuntMatch

        profile_rows = []
        for state in payload.get("profiles", []):
            profile = db.get(DiscoveredProfile, int(state["id"]))
            if not profile:
                raise ValueError("A Common Pool profile no longer exists and cannot be restored.")
            if profile.status != ARCHIVED_STATUS:
                raise ValueError(
                    "A Common Pool profile changed after this archive. Undo newer pool actions first."
                )
            profile_rows.append((profile, state))

        match_rows = []
        for state in payload.get("matches", []):
            match = db.get(DiscoveryHuntMatch, int(state["id"]))
            if not match:
                raise ValueError("A discovery Hunt match no longer exists and cannot be restored.")
            if match.status != ARCHIVED_STATUS:
                raise ValueError(
                    "A discovery Hunt match changed after this archive. Undo newer actions first."
                )
            match_rows.append((match, state))

        for profile, state in profile_rows:
            profile.status = state.get("status") or "raw"
        for match, state in match_rows:
            match.status = state.get("status") or "raw"
            match.scan_error = state.get("scan_error")
            match.rejection_reason = state.get("rejection_reason")
            approved_at = state.get("approved_at")
            imported_at = state.get("imported_at")
            match.approved_at = datetime.fromisoformat(approved_at) if approved_at else None
            match.imported_at = datetime.fromisoformat(imported_at) if imported_at else None
    elif item.action_type == "create_candidate":
        from app.candidates.models import (
            CandidateIntakeRequest,
            DiscoveredProfile,
        )
        from app.candidates.service import get_candidate, serialize_candidate_profile_state
        from app.communications.models import Communication, CommunicationThread, OutreachEnrollment
        from app.hunts.models import HuntCandidate, PlaybookEntry

        candidate_id = int(payload["candidate_id"])
        candidate = get_candidate(db, candidate_id)
        if not candidate:
            raise ValueError("The created Candidate no longer exists.")
        if serialize_candidate_profile_state(candidate) != payload.get("initial_state"):
            raise ValueError(
                "Candidate changed after creation. Undo later Candidate actions first."
            )
        if {row.id for row in candidate.tags or []} != {
            int(value) for value in payload.get("initial_tag_ids", [])
        }:
            raise ValueError("Candidate tags changed after creation. Undo those changes first.")
        if candidate.notes or candidate.snapshots:
            raise ValueError("Candidate gained notes or snapshots. Undo cannot remove that work.")

        for model in (
            DiscoveredProfile,
            CommunicationThread,
            Communication,
            OutreachEnrollment,
            CandidateIntakeRequest,
            PlaybookEntry,
        ):
            if (
                db.scalar(select(model.id).where(model.candidate_id == candidate_id).limit(1))
                is not None
            ):
                raise ValueError(
                    "Candidate has dependent workflow history. Undo it before creation Undo."
                )

        allowed_hunt_id = payload.get("hunt_candidate_id")
        hunt_rows = list(
            db.scalars(
                select(HuntCandidate).where(HuntCandidate.candidate_id == candidate_id)
            ).all()
        )
        expected_hunts = {int(allowed_hunt_id)} if allowed_hunt_id else set()
        if {row.id for row in hunt_rows} != expected_hunts:
            raise ValueError(
                "Candidate Hunt enrollments changed after creation. Undo those changes first."
            )
        if hunt_rows:
            if {row.id for row in hunt_rows[0].activities or []} != {
                int(value) for value in payload.get("hunt_activity_ids", [])
            }:
                raise ValueError(
                    "Candidate pipeline activity changed. Undo cannot remove that history."
                )
            db.delete(hunt_rows[0])
            db.flush()
        db.delete(candidate)
        deleted_candidate_id = candidate_id
    elif item.action_type == "add_candidate_tag":
        from app.candidates.models import CandidateTag

        tag = db.get(CandidateTag, int(payload["tag_id"]))
        if tag:
            db.delete(tag)
    elif item.action_type == "remove_candidate_tag":
        from app.candidates.models import Candidate, CandidateTag

        candidate_id = int(payload["candidate_id"])
        if not db.get(Candidate, candidate_id):
            raise ValueError("The candidate no longer exists, so the tag cannot be restored.")
        existing = db.scalar(
            select(CandidateTag).where(
                CandidateTag.candidate_id == candidate_id,
                CandidateTag.tag_name.ilike(str(payload["tag_name"])),
            )
        )
        if not existing:
            db.add(
                CandidateTag(
                    candidate_id=candidate_id,
                    tag_name=str(payload["tag_name"]),
                    color=payload.get("color"),
                )
            )
    elif item.action_type == "add_candidate_note":
        from app.candidates.models import CandidateNote

        note = db.get(CandidateNote, int(payload["note_id"]))
        if note:
            db.delete(note)
    elif item.action_type == "set_candidate_rogue":
        from app.candidates.models import Candidate, CandidateTag
        from app.hunts.models import PlaybookEntry
        from app.hunts.playbook import ROGUE_TAG

        candidate_id = int(payload["candidate_id"])
        if not db.get(Candidate, candidate_id):
            raise ValueError("The candidate no longer exists, so Rogue status cannot be restored.")
        for tag in list(
            db.scalars(
                select(CandidateTag).where(
                    CandidateTag.candidate_id == candidate_id,
                    CandidateTag.tag_name == ROGUE_TAG,
                )
            ).all()
        ):
            db.delete(tag)
        for tag in payload.get("previous_tags", []):
            db.add(
                CandidateTag(
                    candidate_id=candidate_id,
                    tag_name=tag.get("tag_name") or ROGUE_TAG,
                    color=tag.get("color"),
                )
            )
        playbook_entry_id = payload.get("playbook_entry_id")
        if playbook_entry_id:
            entry = db.get(PlaybookEntry, int(playbook_entry_id))
            if entry:
                db.delete(entry)
    elif item.action_type == "create_hunt":
        from app.candidates.models import CandidateIntakeRequest, DiscoveryHuntMatch
        from app.hunts.models import HuntActivity, HuntCandidate, PlaybookEntry, TalentHunt
        from app.jobs.models import BackgroundJob

        hunt_id = int(payload["hunt_id"])
        hunt = db.get(TalentHunt, hunt_id)
        if not hunt:
            raise ValueError("The created Talent Hunt no longer exists.")
        for model in (
            HuntCandidate,
            DiscoveryHuntMatch,
            CandidateIntakeRequest,
            PlaybookEntry,
            BackgroundJob,
        ):
            if db.scalar(select(model).where(model.hunt_id == hunt_id).limit(1)) is not None:
                raise ValueError(
                    "The Hunt has workflow history. Undo that work before Hunt creation Undo."
                )
        if {stage.id for stage in hunt.stages or []} != {
            int(value) for value in payload.get("initial_stage_ids", [])
        }:
            raise ValueError("The Hunt Pipeline stages changed. Undo those changes first.")
        if {activity.id for activity in hunt.activities or []} != {
            int(value) for value in payload.get("initial_activity_ids", [])
        }:
            raise ValueError("The Hunt activity history changed. Undo those changes first.")
        expected_config_id = payload.get("initial_search_config_id")
        if (hunt.search_config.id if hunt.search_config else None) != expected_config_id:
            raise ValueError("The Hunt search configuration changed. Undo those changes first.")
        initial = payload.get("initial_state") or {}
        for field in ("title", "description", "status", "target_role", "location", "salary_range"):
            if getattr(hunt, field) != initial.get(field):
                raise ValueError("The Hunt details changed. Undo those changes first.")
        config_state = initial.get("search_config")
        if config_state and hunt.search_config:
            for field in (
                "keywords",
                "required_skills",
                "preferred_skills",
                "experience_years_min",
                "experience_years_max",
                "locations",
                "industry",
                "remote_policy",
                "target_platforms",
            ):
                if getattr(hunt.search_config, field) != config_state.get(field):
                    raise ValueError(
                        "The Hunt search configuration changed. Undo those changes first."
                    )
        db.delete(hunt)
    elif item.action_type == "update_hunt":
        from app.hunts.models import HuntSearchConfig, TalentHunt

        state = payload.get("hunt_state") or {}
        hunt = db.get(TalentHunt, int(payload["hunt_id"]))
        if not hunt:
            raise ValueError("The Talent Hunt no longer exists.")
        for field in ("title", "description", "status", "target_role", "location", "salary_range"):
            setattr(hunt, field, state.get(field))
        config_state = state.get("search_config")
        if config_state is None:
            if hunt.search_config:
                db.delete(hunt.search_config)
        else:
            config = hunt.search_config
            if not config:
                config = HuntSearchConfig(id=config_state.get("id"), hunt_id=hunt.id)
                db.add(config)
            for field in (
                "keywords",
                "required_skills",
                "preferred_skills",
                "experience_years_min",
                "experience_years_max",
                "locations",
                "industry",
                "remote_policy",
                "target_platforms",
            ):
                setattr(config, field, config_state.get(field))
    elif item.action_type == "set_hunt_status":
        from app.hunts.models import TalentHunt

        hunt = db.get(TalentHunt, int(payload["hunt_id"]))
        if not hunt:
            raise ValueError("The Talent Hunt no longer exists.")
        hunt.status = payload.get("previous_status") or "Paused"
    elif item.action_type == "add_playbook_insight":
        from app.hunts.models import PlaybookEntry

        entry = db.get(PlaybookEntry, int(payload["playbook_entry_id"]))
        if entry:
            if entry.entry_type != "insight":
                raise ValueError("The Playbook entry is no longer an insight.")
            db.delete(entry)
    elif item.action_type == "create_intake_request":
        from app.candidates.models import CandidateIntakeRequest

        request = db.get(CandidateIntakeRequest, int(payload["request_id"]))
        if request:
            if request.submissions:
                raise ValueError("The Intake link has a submission and can no longer be removed.")
            if request.status not in {"draft", "sent", "expired"}:
                raise ValueError("The Intake request has progressed. Undo its later actions first.")
            db.delete(request)
    elif item.action_type == "review_intake_submission":
        from app.candidates.models import CandidateIntakeRequest, CandidateIntakeSubmission

        request = db.get(CandidateIntakeRequest, int(payload["request_id"]))
        submission = db.get(CandidateIntakeSubmission, int(payload["submission_id"]))
        if not request or not submission:
            raise ValueError("The Intake submission history no longer exists.")
        request.status = payload.get("request_status") or "submitted"
        submission.review_status = payload.get("review_status") or "pending"
        reviewed_at = payload.get("reviewed_at")
        submission.reviewed_at = datetime.fromisoformat(reviewed_at) if reviewed_at else None
    elif item.action_type == "archive_hunt":
        from app.hunts.models import TalentHunt

        hunt = db.get(TalentHunt, int(payload["hunt_id"]))
        if not hunt:
            raise ValueError("The archived Talent Hunt no longer exists.")
        hunt.status = payload.get("previous_status") or "Paused"
    elif item.action_type == "move_pipeline_candidate":
        from app.hunts.models import HuntActivity, HuntCandidate, HuntStage

        candidate = db.get(HuntCandidate, int(payload["hunt_candidate_id"]))
        stage_id = payload.get("stage_id")
        stage = db.get(HuntStage, int(stage_id)) if stage_id is not None else None
        if not candidate:
            raise ValueError("The pipeline candidate no longer exists and cannot be moved back.")
        if stage_id is not None and (not stage or stage.hunt_id != candidate.hunt_id):
            raise ValueError("The original pipeline stage no longer exists.")
        current_name = candidate.stage.name if candidate.stage else "Unassigned"
        candidate.stage_id = int(stage_id) if stage_id is not None else None
        db.add(
            HuntActivity(
                hunt_id=candidate.hunt_id,
                candidate_id=candidate.id,
                activity_type="stage_change_undone",
                description=(
                    f"Undo moved candidate '{candidate.full_name}' from {current_name} "
                    f"to {payload.get('stage_name') or 'Unassigned'}."
                ),
            )
        )
    elif item.action_type == "enroll_pipeline_candidate":
        from app.candidates.models import Candidate, CandidateTag
        from app.hunts.models import HuntActivity, HuntCandidate, TalentHunt

        candidate_id = int(payload["candidate_id"])
        if not db.get(Candidate, candidate_id):
            raise ValueError("The canonical Candidate no longer exists.")
        if payload.get("created_enrollment"):
            enrollment = db.get(HuntCandidate, int(payload["hunt_candidate_id"]))
            if enrollment:
                expected = {int(value) for value in payload.get("created_activity_ids", [])}
                if {row.id for row in enrollment.activities or []} != expected:
                    raise ValueError("Pipeline activity changed. Undo those later actions first.")
                db.delete(enrollment)
                db.flush()
        created_tag_id = payload.get("created_tag_id")
        if created_tag_id:
            tag = db.get(CandidateTag, int(created_tag_id))
            if tag:
                db.delete(tag)
        for row in payload.get("removed_rows", []):
            hunt_id = int(row["hunt_id"])
            if not db.get(TalentHunt, hunt_id):
                continue
            duplicate = db.scalar(
                select(HuntCandidate).where(
                    HuntCandidate.hunt_id == hunt_id,
                    HuntCandidate.candidate_id == candidate_id,
                )
            )
            if duplicate:
                raise ValueError("A later enrollment exists in a previous Hunt. Undo it first.")
            values = {
                key: row.get(key)
                for key in (
                    "id",
                    "hunt_id",
                    "candidate_id",
                    "stage_id",
                    "full_name",
                    "email",
                    "phone",
                    "current_title",
                    "current_company",
                    "location",
                    "linkedin_url",
                    "github_url",
                    "portfolio_url",
                    "match_score",
                    "ai_summary",
                    "notes",
                    "source_platform",
                    "source_query",
                    "status",
                )
            }
            for date_key in ("created_at", "updated_at"):
                if row.get(date_key):
                    values[date_key] = datetime.fromisoformat(row[date_key])
            restored = HuntCandidate(**values)
            db.add(restored)
            db.flush()
            for activity in row.get("activities", []):
                created_at = activity.get("created_at")
                db.add(
                    HuntActivity(
                        id=activity.get("id"),
                        hunt_id=hunt_id,
                        candidate_id=restored.id,
                        activity_type=activity.get("activity_type") or "restored_activity",
                        description=activity.get("description") or "Restored Pipeline activity.",
                        metadata_json=activity.get("metadata_json"),
                        created_at=datetime.fromisoformat(created_at) if created_at else _utcnow(),
                    )
                )
        for tag in payload.get("removed_tags", []):
            duplicate = db.scalar(
                select(CandidateTag).where(
                    CandidateTag.candidate_id == candidate_id,
                    CandidateTag.tag_name == tag.get("tag_name"),
                )
            )
            if not duplicate:
                db.add(
                    CandidateTag(
                        id=tag.get("id"),
                        candidate_id=candidate_id,
                        tag_name=tag.get("tag_name"),
                        color=tag.get("color"),
                    )
                )
    elif item.action_type in {"remove_pipeline_candidate", "triage_pipeline_candidate"}:
        from app.candidates.models import Candidate, CandidateTag
        from app.hunts.models import HuntActivity, HuntCandidate, PlaybookEntry, TalentHunt

        row = payload.get("row") or {}
        hunt_id = int(payload.get("hunt_id") or row.get("hunt_id"))
        if not db.get(TalentHunt, hunt_id):
            raise ValueError(
                "The Talent Hunt no longer exists, so the enrollment cannot be restored."
            )
        candidate_id = row.get("candidate_id")
        if candidate_id is not None and not db.get(Candidate, int(candidate_id)):
            raise ValueError("The canonical Candidate no longer exists.")

        existing = db.get(HuntCandidate, int(row["id"]))
        if not existing and candidate_id is not None:
            existing = db.scalar(
                select(HuntCandidate).where(
                    HuntCandidate.hunt_id == hunt_id,
                    HuntCandidate.candidate_id == int(candidate_id),
                )
            )
        decision = payload.get("decision")
        if decision == "keep":
            if not existing:
                raise ValueError("The Pipeline enrollment no longer exists.")
            existing.stage_id = row.get("stage_id")
        elif existing:
            raise ValueError("A Pipeline enrollment already exists. Undo that later change first.")
        else:
            values = {
                key: row.get(key)
                for key in (
                    "id",
                    "hunt_id",
                    "candidate_id",
                    "stage_id",
                    "full_name",
                    "email",
                    "phone",
                    "current_title",
                    "current_company",
                    "location",
                    "linkedin_url",
                    "github_url",
                    "portfolio_url",
                    "match_score",
                    "ai_summary",
                    "notes",
                    "source_platform",
                    "source_query",
                    "status",
                )
            }
            for date_key in ("created_at", "updated_at"):
                if row.get(date_key):
                    values[date_key] = datetime.fromisoformat(row[date_key])
            existing = HuntCandidate(**values)
            db.add(existing)
            db.flush()
            for activity in row.get("activities", []):
                created_at = activity.get("created_at")
                db.add(
                    HuntActivity(
                        id=activity.get("id"),
                        hunt_id=hunt_id,
                        candidate_id=existing.id,
                        activity_type=activity.get("activity_type") or "restored_activity",
                        description=activity.get("description") or "Restored Pipeline activity.",
                        metadata_json=activity.get("metadata_json"),
                        created_at=datetime.fromisoformat(created_at) if created_at else _utcnow(),
                    )
                )

        for activity_id in payload.get("created_activity_ids", []):
            activity = db.get(HuntActivity, int(activity_id))
            if activity:
                db.delete(activity)
        playbook_entry_id = payload.get("playbook_entry_id")
        if playbook_entry_id:
            entry = db.get(PlaybookEntry, int(playbook_entry_id))
            if entry:
                db.delete(entry)
        if candidate_id is not None:
            for tag in payload.get("removed_tags", []):
                duplicate = db.scalar(
                    select(CandidateTag).where(
                        CandidateTag.candidate_id == int(candidate_id),
                        CandidateTag.tag_name == tag.get("tag_name"),
                    )
                )
                if not duplicate:
                    db.add(
                        CandidateTag(
                            id=tag.get("id"),
                            candidate_id=int(candidate_id),
                            tag_name=tag.get("tag_name"),
                            color=tag.get("color"),
                        )
                    )
    elif item.action_type == "add_pipeline_stage":
        from app.hunts.models import HuntCandidate, HuntStage

        stage_id = int(payload["stage_id"])
        stage = db.get(HuntStage, stage_id)
        if not stage:
            raise ValueError("The Pipeline stage no longer exists.")
        assigned = db.scalar(
            select(HuntCandidate.id).where(HuntCandidate.stage_id == stage_id).limit(1)
        )
        if assigned is not None:
            raise ValueError("Candidates were moved into this stage. Move them out before Undo.")
        db.delete(stage)
    elif item.action_type == "clear_hunt_candidates":
        from app.candidates.models import Candidate, CandidateTag
        from app.hunts.models import HuntActivity, HuntCandidate, TalentHunt
        from app.hunts.pipeline import hunt_tag_name

        hunt_id = int(payload["hunt_id"])
        hunt = db.get(TalentHunt, hunt_id)
        if not hunt:
            raise ValueError(
                "The Talent Hunt no longer exists, so its enrollments cannot be restored."
            )

        for row in payload.get("rows", []):
            candidate_id = row.get("candidate_id")
            if candidate_id is not None and not db.get(Candidate, int(candidate_id)):
                continue
            existing = db.scalar(
                select(HuntCandidate).where(
                    HuntCandidate.hunt_id == hunt_id,
                    HuntCandidate.candidate_id == candidate_id,
                )
            )
            if existing:
                continue

            values = {
                key: row.get(key)
                for key in (
                    "id",
                    "hunt_id",
                    "candidate_id",
                    "stage_id",
                    "full_name",
                    "email",
                    "phone",
                    "current_title",
                    "current_company",
                    "location",
                    "linkedin_url",
                    "github_url",
                    "portfolio_url",
                    "match_score",
                    "ai_summary",
                    "notes",
                    "source_platform",
                    "source_query",
                    "status",
                )
            }
            for date_key in ("created_at", "updated_at"):
                if row.get(date_key):
                    values[date_key] = datetime.fromisoformat(row[date_key])
            restored = HuntCandidate(**values)
            db.add(restored)
            db.flush()

            if candidate_id is not None:
                tag = hunt_tag_name(hunt.title)
                has_tag = db.scalar(
                    select(CandidateTag).where(
                        CandidateTag.candidate_id == int(candidate_id),
                        CandidateTag.tag_name == tag,
                    )
                )
                if not has_tag:
                    db.add(
                        CandidateTag(
                            candidate_id=int(candidate_id),
                            tag_name=tag,
                            color="#19d3c5",
                        )
                    )

            for activity in row.get("activities", []):
                created_at = activity.get("created_at")
                db.add(
                    HuntActivity(
                        id=activity.get("id"),
                        hunt_id=hunt_id,
                        candidate_id=restored.id,
                        activity_type=activity.get("activity_type") or "restored_activity",
                        description=activity.get("description") or "Restored pipeline activity.",
                        metadata_json=activity.get("metadata_json"),
                        created_at=datetime.fromisoformat(created_at) if created_at else _utcnow(),
                    )
                )
    elif item.action_type == "approve_discovered_profile":
        from app.candidates.models import Candidate, DiscoveredProfile, DiscoveryHuntMatch
        from app.hunts.models import HuntCandidate

        match = db.get(DiscoveryHuntMatch, int(payload["match_id"]))
        profile = db.get(DiscoveredProfile, int(payload["profile_id"]))
        candidate = db.get(Candidate, int(payload["candidate_id"]))
        hunt_id = int(payload["hunt_id"])

        if payload.get("created_enrollment"):
            enrollment = db.scalar(
                select(HuntCandidate).where(
                    HuntCandidate.hunt_id == hunt_id,
                    HuntCandidate.candidate_id == int(payload["candidate_id"]),
                )
            )
            if enrollment:
                db.delete(enrollment)

        if profile:
            profile.status = "raw"
            profile.deep_scanned_at = None
        if candidate and payload.get("created_candidate"):
            other_enrollment = db.scalar(
                select(HuntCandidate).where(
                    HuntCandidate.candidate_id == candidate.id,
                    HuntCandidate.hunt_id != hunt_id,
                )
            )
            if other_enrollment is None:
                if profile:
                    profile.candidate_id = None
                db.delete(candidate)
        if match:
            match.status = "shortlisted"
            match.imported_at = None
            match.scan_error = None
    elif item.action_type == "reject_discovered_profile":
        from app.candidates.models import DiscoveryHuntMatch

        match = db.get(DiscoveryHuntMatch, int(payload["match_id"]))
        if not match:
            raise ValueError("The discovery match no longer exists and cannot be restored.")
        match.status = payload.get("status") or "shortlisted"
        match.scan_error = payload.get("scan_error")
        match.rejection_reason = payload.get("rejection_reason")
        approved_at = payload.get("approved_at")
        match.approved_at = datetime.fromisoformat(approved_at) if approved_at else None
    elif item.action_type == "correct_candidate_timeline":
        from app.candidates.models import Candidate, CandidateExperience

        candidate = db.get(Candidate, int(payload["candidate_id"]))
        if not candidate:
            raise ValueError("The candidate no longer exists, so the timeline cannot be restored.")
        for experience in list(candidate.experiences or []):
            db.delete(experience)
        db.flush()
        for row in payload.get("experiences", []):
            db.add(
                CandidateExperience(
                    candidate_id=candidate.id,
                    company=row.get("company") or "Unknown",
                    title=row.get("title") or "Unknown",
                    location=row.get("location"),
                    start_date=row.get("start_date"),
                    end_date=row.get("end_date"),
                    is_current=bool(row.get("is_current", False)),
                    description=row.get("description"),
                )
            )
        candidate.experience_years = payload.get("experience_years")
        candidate.current_title = payload.get("current_title")
        candidate.current_company = payload.get("current_company")
        if candidate.profile:
            candidate.profile.headline = payload.get("headline")
    elif item.action_type in {"update_candidate_profile", "apply_intake_submission"}:
        from app.candidates.models import (
            CandidateIntakeRequest,
            CandidateIntakeSubmission,
            CandidateNote,
        )
        from app.candidates.service import restore_candidate_profile_state

        candidate = restore_candidate_profile_state(db, payload.get("candidate_state") or {})
        if not candidate:
            raise ValueError("The candidate no longer exists, so the profile cannot be restored.")

        if item.action_type == "apply_intake_submission":
            for note_id in payload.get("created_note_ids", []):
                note = db.get(CandidateNote, int(note_id))
                if note:
                    db.delete(note)
            request = db.get(CandidateIntakeRequest, int(payload["request_id"]))
            submission = db.get(CandidateIntakeSubmission, int(payload["submission_id"]))
            if request:
                request.status = payload.get("request_status") or "submitted"
            if submission:
                submission.review_status = payload.get("review_status") or "pending"
                reviewed_at = payload.get("reviewed_at")
                submission.reviewed_at = (
                    datetime.fromisoformat(reviewed_at) if reviewed_at else None
                )
    elif item.action_type == "merge_candidates":
        from app.candidates.duplicates import undo_candidate_merge

        survivor, source = undo_candidate_merge(db, payload)
    elif item.action_type == "disconnect_site":
        from app.communications.models import BrowserSession

        restored = 0
        for browser_session_id in payload.get("active_session_ids", []):
            browser_session = db.get(BrowserSession, int(browser_session_id))
            if browser_session and browser_session.cookies_json:
                browser_session.is_active = True
                restored += 1
        if not restored:
            raise ValueError("No retained browser session could be reactivated.")
    elif item.action_type == "create_communication_log":
        from app.communications.models import Communication, CommunicationThread

        communication = db.get(Communication, int(payload["communication_id"]))
        if communication:
            db.delete(communication)
            db.flush()
        thread_id = payload.get("created_thread_id")
        if thread_id:
            thread = db.get(CommunicationThread, int(thread_id))
            remaining = db.scalar(
                select(Communication.id).where(Communication.thread_id == int(thread_id)).limit(1)
            )
            if thread and remaining is None:
                db.delete(thread)
    elif item.action_type == "set_communication_status":
        from app.communications.models import Communication

        communication = db.get(Communication, int(payload["communication_id"]))
        if not communication:
            raise ValueError("Communication no longer exists.")
        communication.status = payload["status"]
        communication.sent_at = (
            datetime.fromisoformat(payload["sent_at"]) if payload.get("sent_at") else None
        )
        communication.read_at = (
            datetime.fromisoformat(payload["read_at"]) if payload.get("read_at") else None
        )
    elif item.action_type == "create_message_template":
        from app.communications.models import MessageTemplate

        template = db.get(MessageTemplate, int(payload["template_id"]))
        if template:
            if template.outreach_steps:
                raise ValueError(
                    "Template is now used by an outreach step; remove that dependency before undoing creation."
                )
            db.delete(template)
    elif item.action_type == "update_message_template":
        from app.communications.models import MessageTemplate

        state = payload["template"]
        template = db.get(MessageTemplate, int(state["id"]))
        if not template:
            raise ValueError("Message template no longer exists.")
        template.name = state["name"]
        template.channel = state["channel"]
        template.category = state.get("category")
        template.subject = state.get("subject")
        template.body_template = state["body_template"]
        template.variables_json = json.dumps(state.get("variables", []))
        template.is_active = bool(state["is_active"])
    elif item.action_type == "set_message_template_active":
        from app.communications.models import MessageTemplate

        template = db.get(MessageTemplate, int(payload["template_id"]))
        if not template:
            raise ValueError("Message template no longer exists.")
        template.is_active = bool(payload["is_active"])
    elif item.action_type == "create_outreach_sequence":
        from app.communications.models import OutreachSequence

        sequence = db.get(OutreachSequence, int(payload["sequence_id"]))
        if sequence:
            if sequence.enrollments:
                raise ValueError(
                    "Sequence now has enrollments; remove or undo them before undoing sequence creation."
                )
            expected_steps = {int(value) for value in payload.get("created_step_ids", [])}
            actual_steps = {step.id for step in sequence.steps}
            if actual_steps != expected_steps:
                raise ValueError("Sequence steps changed after creation; undo those changes first.")
            db.delete(sequence)
    elif item.action_type == "update_outreach_sequence":
        from app.communications.models import OutreachSequence

        sequence = db.get(OutreachSequence, int(payload["sequence_id"]))
        if not sequence:
            raise ValueError("Outreach sequence no longer exists.")
        sequence.name = payload["name"]
        sequence.description = payload.get("description")
        sequence.channel = payload["channel"]
    elif item.action_type == "set_outreach_sequence_active":
        from app.communications.models import OutreachSequence

        sequence = db.get(OutreachSequence, int(payload["sequence_id"]))
        if not sequence:
            raise ValueError("Outreach sequence no longer exists.")
        sequence.is_active = bool(payload["is_active"])
    elif item.action_type == "add_outreach_step":
        from app.communications.models import OutreachEnrollment, OutreachStep

        step = db.get(OutreachStep, int(payload["step_id"]))
        if step:
            progressed = db.scalar(
                select(OutreachEnrollment).where(
                    OutreachEnrollment.sequence_id == step.sequence_id,
                    (
                        (OutreachEnrollment.last_step_sent_at.is_not(None))
                        | (OutreachEnrollment.current_step_number > step.step_number)
                    ),
                )
            )
            if progressed:
                raise ValueError(
                    "An enrollment has progressed through this sequence; the step cannot be removed by Undo."
                )
            db.delete(step)
    elif item.action_type == "enroll_outreach_candidate":
        from app.communications.models import OutreachEnrollment

        enrollment = db.get(OutreachEnrollment, int(payload["enrollment_id"]))
        if enrollment:
            if enrollment.last_step_sent_at is not None or enrollment.current_step_number != 1:
                raise ValueError(
                    "This enrollment has already progressed and cannot be removed by Undo."
                )
            db.delete(enrollment)
    elif item.action_type == "set_outreach_enrollment_status":
        from app.communications.models import OutreachEnrollment

        enrollment = db.get(OutreachEnrollment, int(payload["enrollment_id"]))
        if not enrollment:
            raise ValueError("Outreach enrollment no longer exists.")
        enrollment.status = payload["status"]
        enrollment.next_step_due_at = (
            datetime.fromisoformat(payload["next_step_due_at"])
            if payload.get("next_step_due_at")
            else None
        )
    elif item.action_type == "configure_embedded_ai":
        from app.ai.local_server import local_server_manager
        from app.config.preferences import save_app_preferences
        from app.config.settings import settings
        from app.jobs import service as jobs

        active_job = next(
            (
                row
                for row in jobs.list_job_rows(statuses={"running"}, limit=20)
                if row.kind in {"embedded_ai_install", "embedded_ai_start"}
            ),
            None,
        )
        if active_job:
            raise ValueError(
                f"Embedded AI job {active_job.id} is active. Cancel it before Undo."
            )

        current = payload.get("current") or {}
        actual = {
            "mode": settings.local_ai_mode,
            "autostart": bool(settings.local_ai_autostart),
            "host": settings.llama_server_host,
            "port": int(settings.llama_server_port),
        }
        if actual != current:
            raise ValueError(
                "Local AI configuration changed after this action. Undo newer settings first."
            )
        previous = payload.get("previous") or {}
        local_server_manager.stop()
        settings.local_ai_mode = str(previous["mode"])
        settings.local_ai_autostart = bool(previous["autostart"])
        settings.llama_server_host = str(previous["host"])
        settings.llama_server_port = int(previous["port"])
        save_app_preferences()
    else:
        raise ValueError(f"Action type '{item.action_type}' does not have an undo handler yet.")

    item.status = "undone"
    item.undone_at = _utcnow()
    db.commit()
    if item.action_type in {"update_candidate_profile", "apply_intake_submission"}:
        from app.candidates.service import _reindex_candidate

        _reindex_candidate(db, candidate)
    elif item.action_type == "merge_candidates":
        from app.candidates.service import _reindex_candidate

        _reindex_candidate(db, survivor)
        _reindex_candidate(db, source)
    elif item.action_type == "create_candidate":
        from app.candidates.search import candidate_search_index

        candidate_search_index.delete_candidate(deleted_candidate_id)
    db.refresh(item)
    return item


def serialize_action(item: ActionHistory, db: Session | None = None) -> dict[str, Any]:
    result = {
        "id": item.id,
        "action_type": item.action_type,
        "summary": item.summary,
        "actor_type": item.actor_type,
        "session_id": item.session_id,
        "status": item.status,
        "created_at": item.created_at.isoformat(),
        "undo_expires_at": item.undo_expires_at.isoformat() if item.undo_expires_at else None,
        "undoable": is_undoable(item),
    }
    if db is not None:
        result["target"] = action_target(db, item)
        result["resource_keys"] = action_resource_keys(db, item)
    return result
