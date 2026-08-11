"""Recruiter review queue for lightweight web discoveries."""

from __future__ import annotations

from nicegui import ui

from app.actions.api import dispatch_action
from app.candidates.discovery import (
    REVIEWABLE_STATUSES,
    common_pool_count,
    common_pool_linked_candidate_count,
    discovery_counts,
    list_common_pool_profiles,
    list_discoveries,
    recover_stale_enrichments,
    sync_candidate_identities_to_common_pool,
)
from app.hunts.service import list_hunts
from app.infrastructure.db import SessionFactory, init_db
from app.ui.layout import create_layout


def render_discoveries() -> None:
    init_db()
    state = {
        "hunt_id": None,
        "view": "Common Pool",
        "search": "",
        "limit": 100,
        "identities_synced": False,
    }
    list_ref = {"element": None}
    count_ref = {"label": None}

    def selected_statuses() -> tuple[str, ...]:
        if state["view"] == "Imported":
            return ("imported",)
        if state["view"] == "Rejected":
            return ("rejected",)
        return REVIEWABLE_STATUSES

    def refresh() -> None:
        box = list_ref["element"]
        if box is None:
            return
        profiles = []
        matches = []
        with SessionFactory() as db:
            recover_stale_enrichments(db)
            if not state["identities_synced"]:
                sync_candidate_identities_to_common_pool(db)
                state["identities_synced"] = True
            counts = discovery_counts(db, hunt_id=state["hunt_id"])
            total_profiles = common_pool_count(
                db,
                hunt_id=state["hunt_id"],
                search=state["search"],
            )
            linked_candidates = common_pool_linked_candidate_count(
                db,
                hunt_id=state["hunt_id"],
                search=state["search"],
            )
            if state["view"] == "Common Pool":
                profiles = list_common_pool_profiles(
                    db,
                    hunt_id=state["hunt_id"],
                    search=state["search"],
                    limit=state["limit"],
                )
            else:
                matches = list_discoveries(
                    db,
                    hunt_id=state["hunt_id"],
                    statuses=selected_statuses(),
                    limit=500,
                )
        if count_ref["label"]:
            profile_word = "profile" if total_profiles == 1 else "profiles"
            candidate_word = "record" if linked_candidates == 1 else "records"
            count_ref["label"].set_text(
                f"{total_profiles} permanent {profile_word} · "
                f"{counts.get('reviewable', 0)} awaiting review · "
                f"{linked_candidates} candidate {candidate_word}"
            )

        box.clear()
        with box:
            if state["view"] == "Common Pool":
                if not profiles:
                    with ui.column().classes("w-full items-center gap-2 py-14"):
                        ui.icon("group_search", size="42px").classes("text-slate-600")
                        ui.label("No profiles in the Common Pool").classes(
                            "text-base font-semibold text-slate-300"
                        )
                        ui.label("Profiles found by sourcing will appear here.").classes(
                            "text-xs text-slate-500"
                        )
                    return

                for profile in profiles:
                    hunt_names = sorted(
                        {
                            match.hunt.title
                            for match in profile.hunt_matches
                            if match.hunt and match.hunt.title
                        }
                    )
                    match_statuses = sorted(
                        {match.status.replace("_", " ").title() for match in profile.hunt_matches}
                    )
                    with ui.element("div").classes(
                        "w-full border-b border-slate-800 py-4 px-1 flex gap-4 items-start"
                    ):
                        with ui.column().classes("grow min-w-0 gap-1"):
                            with ui.row().classes("items-center gap-2 flex-wrap"):
                                ui.label(profile.full_name or "Unknown candidate").classes(
                                    "text-sm font-bold text-slate-100"
                                )
                                ui.badge(profile.platform.capitalize()).classes("text-[10px]")
                                if profile.candidate_id:
                                    ui.badge("Candidate record").props(
                                        "outline color=teal"
                                    ).classes("text-[10px]")
                                elif match_statuses:
                                    ui.badge(match_statuses[0]).props(
                                        "outline color=blue-grey"
                                    ).classes("text-[10px]")
                            ui.label(profile.headline or "Headline unavailable").classes(
                                "text-xs text-slate-300"
                            )
                            details = []
                            if profile.current_company:
                                details.append(profile.current_company)
                            if profile.location:
                                details.append(profile.location)
                            if profile.experience_years is not None:
                                details.append(f"{profile.experience_years:g} years")
                            if details:
                                ui.label(" · ".join(details)).classes(
                                    "text-[11px] text-slate-500"
                                )
                            provenance = (
                                f"Seen {profile.seen_count or 1} time(s)"
                                + (f" across {len(hunt_names)} hunt(s)" if hunt_names else "")
                            )
                            ui.label(provenance).classes("text-[10px] text-teal-500")
                            if hunt_names:
                                ui.label("Hunts: " + ", ".join(hunt_names[:4])).classes(
                                    "text-[10px] text-slate-500"
                                )
                            if profile.snippet:
                                ui.label(profile.snippet[:280]).classes(
                                    "text-[11px] text-slate-400 leading-relaxed"
                                )

                        with ui.row().classes("items-center gap-1 shrink-0"):
                            ui.button(
                                icon="open_in_new",
                                on_click=lambda url=profile.source_url: ui.navigate.to(url, new_tab=True),
                            ).props("flat round dense").classes("text-sky-400").tooltip(
                                "Open source profile"
                            )
                            if profile.candidate_id:
                                ui.button(
                                    icon="person",
                                    on_click=lambda cid=profile.candidate_id: ui.navigate.to(
                                        f"/candidates/{cid}"
                                    ),
                                ).props("flat round dense").classes("text-teal-400").tooltip(
                                    "Open candidate record"
                                )

                if len(profiles) < total_profiles:
                    def load_more() -> None:
                        state["limit"] += 100
                        refresh()

                    with ui.row().classes("w-full justify-center py-4"):
                        ui.button(
                            f"Load more ({len(profiles)} of {total_profiles})",
                            icon="expand_more",
                            on_click=load_more,
                        ).props("flat no-caps").classes("text-teal-400")
                return

            if not matches:
                with ui.column().classes("w-full items-center gap-2 py-14"):
                    ui.icon("person_search", size="42px").classes("text-slate-600")
                    ui.label("No profiles in this view").classes("text-base font-semibold text-slate-300")
                    ui.label("Run a hunt search to populate the review queue.").classes("text-xs text-slate-500")
                return

            for match in matches:
                profile = match.profile
                hunt = match.hunt
                with ui.element("div").classes(
                    "w-full border-b border-slate-800 py-4 px-1 flex gap-4 items-start"
                ):
                    with ui.column().classes("grow min-w-0 gap-1"):
                        with ui.row().classes("items-center gap-2 flex-wrap"):
                            ui.label(profile.full_name or "Unknown candidate").classes(
                                "text-sm font-bold text-slate-100"
                            )
                            ui.badge(profile.platform.capitalize()).classes("text-[10px]")
                            ui.badge(match.status.replace("_", " ").title()).props(
                                "outline color=teal"
                            ).classes("text-[10px]")
                        ui.label(profile.headline or "Headline unavailable").classes(
                            "text-xs text-slate-300"
                        )
                        details = [hunt.title]
                        if profile.location:
                            details.append(profile.location)
                        if profile.experience_years is not None:
                            details.append(f"{profile.experience_years:g} years")
                        ui.label(" · ".join(details)).classes("text-[11px] text-slate-500")
                        if profile.snippet:
                            ui.label(profile.snippet[:360]).classes(
                                "text-[11px] text-slate-400 leading-relaxed"
                            )
                        if match.scan_error:
                            ui.label(f"Deep scan failed: {match.scan_error}").classes(
                                "text-[11px] text-red-400"
                            )
                        if match.rejection_reason:
                            ui.label(f"Filtered reason: {match.rejection_reason}").classes(
                                "text-[11px] text-amber-300"
                            )

                    with ui.row().classes("items-center gap-1 shrink-0"):
                        ui.button(
                            icon="open_in_new",
                            on_click=lambda url=profile.source_url: ui.navigate.to(url, new_tab=True),
                        ).props("flat round dense").classes("text-sky-400").tooltip("Open source profile")

                        if match.status in {"shortlisted", "scan_failed"}:
                            def approve(
                                mid=match.id,
                                name=profile.full_name or "candidate",
                                hid=match.hunt_id,
                                retrying=match.status == "scan_failed",
                            ):
                                result = dispatch_action(
                                    "discoveries.approve",
                                    {"match_id": mid},
                                    actor_type="ui",
                                    session_id=f"hunt_{hid}",
                                )
                                ui.notify(
                                    (
                                        f"{'Retry' if retrying else 'Deep scan'} started for {name}"
                                        if result.success else result.error
                                    ),
                                    type="info" if result.success else "negative",
                                )
                                refresh()

                            ui.button(
                                icon="refresh" if match.status == "scan_failed" else "check",
                                on_click=approve,
                            ).props(
                                "flat round dense"
                            ).classes("text-teal-400").tooltip(
                                "Retry deep scan" if match.status == "scan_failed" else "Approve and deep scan"
                            )

                            def reject(mid=match.id, name=profile.full_name or "candidate", hid=match.hunt_id):
                                result = dispatch_action(
                                    "discoveries.reject",
                                    {"match_id": mid, "reason": "Recruiter passed"},
                                    actor_type="ui",
                                    session_id=f"hunt_{hid}",
                                )
                                ui.notify(
                                    f"Passed on {name}. Undo is available in Action History."
                                    if result.success else result.error,
                                    type="warning" if result.success else "negative",
                                )
                                refresh()

                            ui.button(icon="close", on_click=reject).props(
                                "flat round dense"
                            ).classes("text-slate-500").tooltip("Reject discovery")
                        elif match.status in {"approved", "enriching"}:
                            ui.spinner("dots", size="20px").classes("text-teal-400")
                        elif match.status == "imported" and profile.candidate_id:
                            ui.button(
                                icon="person",
                                on_click=lambda cid=profile.candidate_id: ui.navigate.to(f"/candidates/{cid}"),
                            ).props("flat round dense").classes("text-teal-400").tooltip("Open candidate")

    with ui.column().classes("w-full gap-4"):
        with ui.row().classes("w-full justify-between items-end flex-wrap gap-3"):
            with ui.column().classes("gap-0"):
                ui.label("TALENT SOURCING").classes("th-ey")
                ui.label("Common Talent Pool").classes("th-title")
                count_ref["label"] = ui.label("").classes("th-muted")

            with SessionFactory() as db:
                hunts = list_hunts(db)
            hunt_options = {None: "All hunts", **{hunt.id: hunt.title for hunt in hunts}}

            with ui.row().classes("items-center gap-2 flex-wrap"):
                search_input = ui.input(
                    value="",
                    placeholder="Search common pool...",
                ).props("dark outlined dense clearable debounce=250").classes("w-64")
                hunt_select = ui.select(
                    hunt_options,
                    value=None,
                    label="Hunt",
                ).classes("w-52").props("dark outlined dense")
                view_toggle = ui.toggle(
                    ["Common Pool", "Review", "Imported", "Rejected"],
                    value="Common Pool",
                ).props("dense no-caps")

        with ui.element("div").classes(
            "w-full border border-slate-800 rounded-lg px-4 bg-[#0b1925]"
        ) as list_box:
            list_ref["element"] = list_box

        def filters_changed() -> None:
            state["hunt_id"] = hunt_select.value
            state["view"] = view_toggle.value
            state["search"] = search_input.value or ""
            state["limit"] = 100
            refresh()

        search_input.on_value_change(lambda _: filters_changed())
        hunt_select.on_value_change(lambda _: filters_changed())
        view_toggle.on_value_change(lambda _: filters_changed())
        refresh()
        ui.timer(2.0, refresh)


def discoveries_page() -> None:
    create_layout(render_discoveries, active_path="/discoveries")
