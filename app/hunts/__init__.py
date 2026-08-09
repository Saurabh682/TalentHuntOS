"""TalentHunt campaigns and pipeline module."""

from app.hunts.models import (
    TalentHunt,
    HuntSearchConfig,
    HuntStage,
    HuntCandidate,
    HuntActivity,
    PlaybookEntry,
)
from app.hunts.service import (
    create_hunt,
    get_hunt,
    list_hunts,
    update_hunt,
    delete_hunt,
    get_hunt_metrics,
)
from app.hunts.pipeline import (
    move_candidate_stage,
    add_candidate_to_hunt,
    get_pipeline_data,
    add_stage_to_hunt,
    remove_candidate,
)
from app.hunts.playbook import (
    list_playbook_entries,
    keep_hunt_candidate,
    pass_hunt_candidate,
    add_insight,
)

__all__ = [
    "TalentHunt",
    "HuntSearchConfig",
    "HuntStage",
    "HuntCandidate",
    "HuntActivity",
    "PlaybookEntry",
    "create_hunt",
    "get_hunt",
    "list_hunts",
    "update_hunt",
    "delete_hunt",
    "get_hunt_metrics",
    "move_candidate_stage",
    "add_candidate_to_hunt",
    "get_pipeline_data",
    "add_stage_to_hunt",
    "remove_candidate",
    "list_playbook_entries",
    "keep_hunt_candidate",
    "pass_hunt_candidate",
    "add_insight",
]
