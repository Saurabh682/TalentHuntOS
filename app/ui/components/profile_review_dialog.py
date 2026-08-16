"""Shared recruiter review UI for extracted / intake profile sections."""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, List, Optional

from nicegui import ui

from app.actions.api import dispatch_action


def open_profile_sections_review(
    candidate_id: int,
    draft: Dict[str, Any],
    *,
    title: str = "Review extracted profile",
    default_mode: str = "merge",
    on_applied: Optional[Callable[[], None]] = None,
    action_name: str = "candidates.profile.apply",
    action_extra: Optional[Dict[str, Any]] = None,
    nested_payload_key: Optional[str] = None,
) -> None:
    """Show editable checklist of experiences / education / skills, then apply."""
    experiences: List[Dict[str, Any]] = list(draft.get("experiences") or [])
    educations: List[Dict[str, Any]] = list(draft.get("educations") or [])
    skills: List[str] = list(draft.get("skills") or [])
    headline = draft.get("headline")
    summary = draft.get("summary")
    years = draft.get("experience_years")
    highlights: List[str] = list(draft.get("highlights") or [])

    exp_checks: List[Any] = []
    edu_checks: List[Any] = []
    skill_checks: List[Any] = []

    with ui.dialog() as dialog, ui.card().classes(
        "w-full max-w-3xl p-5 th-card border border-teal-500/40 gap-3"
    ):
        ui.label(title).classes("text-lg font-bold text-slate-100")
        meta_bits = []
        if headline:
            meta_bits.append(str(headline))
        if draft.get("location"):
            meta_bits.append(str(draft["location"]))
        if years is not None:
            meta_bits.append(f"{years} yrs exp")
        if meta_bits:
            ui.label(" · ".join(meta_bits)).classes("text-xs text-teal-300")
        if summary:
            ui.label(str(summary)[:400]).classes("text-xs text-slate-400")
        if highlights:
            ui.label("Highlights").classes("text-xs font-semibold text-slate-200")
            for item in highlights:
                ui.label(str(item)).classes("text-[11px] text-amber-200")

        mode_sel = ui.toggle(
            {"merge": "Merge with existing", "replace": "Replace sections"},
            value=default_mode if default_mode in ("merge", "replace") else "merge",
        ).props("dense").classes("text-xs")

        with ui.scroll_area().classes("w-full h-[420px]"):
            with ui.column().classes("w-full gap-4 p-1"):
                ui.label("Work experience").classes("text-sm font-semibold text-slate-200")
                if not experiences:
                    ui.label("No experience rows extracted.").classes("text-xs text-slate-500 italic")
                for i, exp in enumerate(experiences):
                    label = f"{exp.get('title') or '?'} @ {exp.get('company') or '?'}"
                    dates = f"{exp.get('start_date') or ''} – {'Present' if exp.get('is_current') else (exp.get('end_date') or '')}"
                    if exp.get("employment_type"):
                        dates = f"{dates} · {exp['employment_type']}"
                    with ui.row().classes("w-full items-start gap-2"):
                        chk = ui.checkbox(value=True).classes("text-slate-300")
                        exp_checks.append(chk)
                        with ui.column().classes("gap-0 grow"):
                            ui.label(label).classes("text-xs font-semibold text-slate-100")
                            ui.label(dates).classes("text-[11px] text-slate-500")
                            if exp.get("description"):
                                ui.label(str(exp["description"])[:220]).classes(
                                    "text-[11px] text-slate-400"
                                )
                            if exp.get("skills"):
                                ui.label(" · ".join(exp["skills"])).classes(
                                    "text-[11px] text-teal-300"
                                )

                ui.label("Education").classes("text-sm font-semibold text-slate-200 mt-2")
                if not educations:
                    ui.label("No education rows extracted.").classes("text-xs text-slate-500 italic")
                for edu in educations:
                    label = edu.get("institution") or "?"
                    deg = " · ".join(
                        x for x in [edu.get("degree"), edu.get("field_of_study")] if x
                    )
                    with ui.row().classes("w-full items-start gap-2"):
                        chk = ui.checkbox(value=True).classes("text-slate-300")
                        edu_checks.append(chk)
                        with ui.column().classes("gap-0 grow"):
                            ui.label(label).classes("text-xs font-semibold text-slate-100")
                            if deg:
                                ui.label(deg).classes("text-[11px] text-slate-400")
                            details = [edu.get("grade"), edu.get("activities"), edu.get("description")]
                            if any(details):
                                ui.label(" · ".join(str(item) for item in details if item)).classes(
                                    "text-[11px] text-slate-500"
                                )

                ui.label("Skills").classes("text-sm font-semibold text-slate-200 mt-2")
                if not skills:
                    ui.label("No skills extracted.").classes("text-xs text-slate-500 italic")
                else:
                    with ui.row().classes("gap-2 flex-wrap"):
                        for sk in skills:
                            chk = ui.checkbox(sk, value=True).classes("text-xs text-teal-300")
                            skill_checks.append((chk, sk))

        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button("Cancel", on_click=dialog.close).props("flat").classes("text-slate-400 text-xs")

            def apply_selected():
                selected_exp = [
                    experiences[i]
                    for i, chk in enumerate(exp_checks)
                    if chk.value and i < len(experiences)
                ]
                selected_edu = [
                    educations[i]
                    for i, chk in enumerate(edu_checks)
                    if chk.value and i < len(educations)
                ]
                selected_skills = [sk for chk, sk in skill_checks if chk.value]
                if (
                    not selected_exp and not selected_edu and not selected_skills
                    and not summary and years is None and not draft.get("resume_text")
                ):
                    ui.notify("Nothing selected to apply.", type="warning")
                    return
                mode = mode_sel.value if isinstance(mode_sel.value, str) else "merge"
                profile_payload = {
                        "candidate_id": candidate_id,
                        "experiences": selected_exp or None,
                        "educations": selected_edu or None,
                        "skills": selected_skills if selected_skills or mode == "replace" else None,
                        "highlights": highlights or None,
                        "full_name": draft.get("full_name"),
                        "email": draft.get("email"),
                        "phone": draft.get("phone"),
                        "location": draft.get("location"),
                        "current_title": draft.get("current_title"),
                        "current_company": draft.get("current_company"),
                        "pronouns": draft.get("pronouns"),
                        "connection_degree": draft.get("connection_degree"),
                        "connections_count": draft.get("connections_count"),
                        "profile_image_url": draft.get("profile_image_url"),
                        "headline": headline,
                        "summary": summary,
                        "resume_text": draft.get("resume_text"),
                        "experience_years": float(years) if years is not None else None,
                        "mode": mode,
                    }
                if nested_payload_key:
                    profile_payload.pop("candidate_id", None)
                    profile_payload.pop("mode", None)
                    action_payload = {
                        **(action_extra or {}),
                        "mode": mode,
                        nested_payload_key: profile_payload,
                    }
                else:
                    action_payload = {**profile_payload, **(action_extra or {})}
                result = dispatch_action(
                    action_name,
                    action_payload,
                    actor_type="ui",
                    session_id=f"candidate_{candidate_id}",
                )
                if not result.success:
                    ui.notify(result.error or "Failed to apply profile sections.", type="negative")
                    return
                ui.notify("Profile sections updated.", type="positive")
                dialog.close()
                if on_applied:
                    on_applied()
                else:
                    ui.navigate.to(f"/candidates/{candidate_id}")

            ui.button("Apply to profile", icon="save", on_click=apply_selected).classes(
                "th-primary-btn text-xs"
            )

    dialog.open()


def run_extract_then_review(
    candidate_id: int,
    text: str,
    *,
    title: str = "Review extracted profile",
    on_applied: Optional[Callable[[], None]] = None,
    draft_overrides: Optional[Dict[str, Any]] = None,
) -> None:
    """Show a spinner dialog, extract via LLM off-thread, then open review."""

    with ui.dialog() as wait_dlg, ui.card().classes("p-6 th-card gap-3 min-w-[280px]"):
        with ui.row().classes("items-center gap-3"):
            ui.spinner(size="sm", color="teal")
            ui.label("Extracting structured profile…").classes("text-sm text-slate-200")

    wait_dlg.open()

    async def _run():
        from app.candidates.profile_extract import extract_profile_from_text, extract_result_to_dict

        result = await asyncio.to_thread(extract_profile_from_text, text)
        wait_dlg.close()
        draft = extract_result_to_dict(result)
        draft["resume_text"] = text[:200_000]
        for key, value in (draft_overrides or {}).items():
            if value not in (None, ""):
                draft[key] = value
        if result.status != "success":
            ui.notify(result.error or "Extract failed.", type="warning")
            if not draft.get("experiences") and not draft.get("skills"):
                return
        open_profile_sections_review(
            candidate_id,
            draft,
            title=title,
            on_applied=on_applied,
        )

    ui.timer(0.05, lambda: asyncio.create_task(_run()), once=True)
