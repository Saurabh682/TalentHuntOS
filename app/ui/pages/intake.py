"""Public candidate intake form (magic-link, no recruiter chrome)."""

from __future__ import annotations

from nicegui import ui

from app.infrastructure.db import SessionFactory, init_db
from app.candidates.service import get_candidate
from app.candidates.intake_service import (
    get_intake_by_token,
    get_hunt_jd_context,
    is_intake_open,
    submit_intake,
)


def _shell(content_fn):
    """Minimal dark shell without Copilot / app nav."""
    ui.colors(primary="#19d3c5")
    ui.query("body").classes("bg-[#0a1219]")
    with ui.column().classes("w-full min-h-screen items-center px-4 py-8"):
        with ui.column().classes("w-full max-w-2xl gap-4"):
            content_fn()


def render_intake_form(token: str):
    init_db()

    with SessionFactory() as db:
        req = get_intake_by_token(db, token)
        if not req:
            def missing():
                ui.label("TalentHunt OS").classes("text-sm font-semibold text-teal-400")
                ui.label("This form link is invalid.").classes("text-xl text-slate-100 font-bold")
                ui.label("Ask your recruiter for a new link.").classes("text-sm text-slate-400")
            _shell(missing)
            return

        open_ok, reason = is_intake_open(req)
        candidate = get_candidate(db, req.candidate_id)
        jd = get_hunt_jd_context(db, req.hunt_id)
        cand_name = candidate.full_name if candidate else "Candidate"
        email_default = (candidate.email or "") if candidate else ""
        phone_default = (candidate.phone or "") if candidate else ""
        loc_default = (candidate.location or "") if candidate else ""

        if not open_ok:
            msg = reason

            def closed():
                ui.label("TalentHunt OS").classes("text-sm font-semibold text-teal-400")
                ui.label("Form unavailable").classes("text-xl text-slate-100 font-bold")
                ui.label(msg).classes("text-sm text-slate-400")
            _shell(closed)
            return

        exp_widgets: list[dict] = []
        edu_widgets: list[dict] = []

        def body():
            nonlocal exp_widgets, edu_widgets
            ui.label("TalentHunt OS").classes("text-sm font-semibold text-teal-400 tracking-wide")
            ui.label("Candidate profile form").classes("text-2xl font-bold text-slate-50")
            first = cand_name.split()[0] if cand_name else "there"
            ui.label(f"Hi {first} — please confirm your details below.").classes("text-sm text-slate-400")

            if jd:
                with ui.card().classes("w-full p-4 bg-[#0e1b28] border border-teal-900/50 gap-2 rounded-lg"):
                    ui.label("Role you're being considered for").classes(
                        "text-xs font-semibold text-teal-300 uppercase tracking-wide"
                    )
                    ui.label(jd.get("role") or jd.get("title") or "Open role").classes(
                        "text-lg font-bold text-slate-100"
                    )
                    bits = []
                    if jd.get("location"):
                        bits.append(str(jd["location"]))
                    if jd.get("salary_range"):
                        bits.append(str(jd["salary_range"]))
                    if jd.get("required_skills"):
                        bits.append(f"Skills: {jd['required_skills']}")
                    if bits:
                        ui.label(" · ".join(bits)).classes("text-xs text-slate-400")
                    if jd.get("description"):
                        ui.label(str(jd["description"])[:800]).classes(
                            "text-sm text-slate-300 leading-relaxed mt-1"
                        )

            with ui.card().classes("w-full p-4 bg-[#0e1b28] border border-slate-800 gap-3 rounded-lg"):
                ui.label("Contact").classes("text-sm font-bold text-slate-100")
                email_in = ui.input("Email", value=email_default).classes("w-full").props("outlined dark dense")
                phone_in = ui.input("Phone", value=phone_default).classes("w-full").props("outlined dark dense")
                loc_in = ui.input("Location", value=loc_default).classes("w-full").props("outlined dark dense")

            exp_container = ui.column().classes("w-full gap-3")

            def add_exp_row(seed: dict | None = None):
                seed = seed or {}
                with exp_container:
                    with ui.card().classes("w-full p-4 bg-[#0e1b28] border border-slate-800 gap-2 rounded-lg"):
                        if not exp_widgets:
                            ui.label("Work experience").classes("text-sm font-bold text-slate-100")
                        c = ui.input("Company", value=seed.get("company") or "").classes("w-full").props("outlined dark dense")
                        t = ui.input("Title", value=seed.get("title") or "").classes("w-full").props("outlined dark dense")
                        with ui.row().classes("w-full gap-2"):
                            s = ui.input("Start (YYYY-MM)", value=seed.get("start_date") or "").classes("grow").props(
                                "outlined dark dense"
                            )
                            e = ui.input("End (YYYY-MM)", value=seed.get("end_date") or "").classes("grow").props(
                                "outlined dark dense"
                            )
                        cur = ui.checkbox("Current role", value=bool(seed.get("is_current"))).classes(
                            "text-xs text-slate-300"
                        )
                        d = ui.textarea("Highlights", value=seed.get("description") or "").classes("w-full").props(
                            "outlined dark dense"
                        )
                        exp_widgets.append(
                            {"company": c, "title": t, "start": s, "end": e, "current": cur, "desc": d}
                        )

            with ui.row().classes("w-full justify-between items-center"):
                ui.label("").classes("grow")
            add_exp_row()
            ui.button("Add another role", icon="add", on_click=lambda: add_exp_row()).props("flat dense").classes(
                "text-xs text-teal-300 self-start"
            )

            edu_container = ui.column().classes("w-full gap-3")

            def add_edu_row(seed: dict | None = None):
                seed = seed or {}
                with edu_container:
                    with ui.card().classes("w-full p-4 bg-[#0e1b28] border border-slate-800 gap-2 rounded-lg"):
                        if not edu_widgets:
                            ui.label("Education").classes("text-sm font-bold text-slate-100")
                        inst = ui.input("Institution", value=seed.get("institution") or "").classes("w-full").props(
                            "outlined dark dense"
                        )
                        deg = ui.input("Degree", value=seed.get("degree") or "").classes("w-full").props(
                            "outlined dark dense"
                        )
                        field = ui.input("Field of study", value=seed.get("field_of_study") or "").classes("w-full").props(
                            "outlined dark dense"
                        )
                        ey = ui.input("Graduation year", value=str(seed.get("end_year") or "")).classes("w-full").props(
                            "outlined dark dense"
                        )
                        edu_widgets.append(
                            {"institution": inst, "degree": deg, "field": field, "end_year": ey}
                        )

            add_edu_row()
            ui.button("Add another school", icon="add", on_click=lambda: add_edu_row()).props("flat dense").classes(
                "text-xs text-amber-300 self-start"
            )

            with ui.card().classes("w-full p-4 bg-[#0e1b28] border border-slate-800 gap-3 rounded-lg"):
                ui.label("Skills").classes("text-sm font-bold text-slate-100")
                skills_in = ui.input(
                    "Comma-separated skills",
                    placeholder="e.g. Salesforce, Cold calling, Negotiation",
                ).classes("w-full").props("outlined dark dense")
                summary_in = ui.textarea("Short professional summary (optional)").classes("w-full").props(
                    "outlined dark dense"
                )

            with ui.card().classes("w-full p-4 bg-[#0e1b28] border border-slate-800 gap-3 rounded-lg"):
                ui.label("Role fit").classes("text-sm font-bold text-slate-100")
                avail = ui.input("Availability / earliest start").classes("w-full").props("outlined dark dense")
                notice = ui.input("Notice period").classes("w-full").props("outlined dark dense")
                salary = ui.input("Salary expectation").classes("w-full").props("outlined dark dense")
                why = ui.textarea("Why are you a fit for this role?").classes("w-full").props("outlined dark dense")

            status = ui.label("").classes("text-xs text-slate-400")

            def do_submit():
                experiences = []
                for w in exp_widgets:
                    company = (w["company"].value or "").strip()
                    title = (w["title"].value or "").strip()
                    if not company or not title:
                        continue
                    experiences.append({
                        "company": company,
                        "title": title,
                        "start_date": (w["start"].value or "").strip() or None,
                        "end_date": (w["end"].value or "").strip() or None,
                        "is_current": bool(w["current"].value),
                        "description": (w["desc"].value or "").strip() or None,
                    })
                educations = []
                for w in edu_widgets:
                    institution = (w["institution"].value or "").strip()
                    if not institution:
                        continue
                    ey_raw = (w["end_year"].value or "").strip()
                    try:
                        end_year = int(ey_raw) if ey_raw else None
                    except ValueError:
                        end_year = None
                    educations.append({
                        "institution": institution,
                        "degree": (w["degree"].value or "").strip() or None,
                        "field_of_study": (w["field"].value or "").strip() or None,
                        "end_year": end_year,
                    })
                skills = [s.strip() for s in (skills_in.value or "").split(",") if s.strip()]
                payload = {
                    "contact": {
                        "email": (email_in.value or "").strip(),
                        "phone": (phone_in.value or "").strip(),
                        "location": (loc_in.value or "").strip(),
                    },
                    "experiences": experiences,
                    "educations": educations,
                    "skills": skills,
                    "summary": (summary_in.value or "").strip() or None,
                    "jd_fit": {
                        "availability": (avail.value or "").strip(),
                        "notice_period": (notice.value or "").strip(),
                        "salary_expectation": (salary.value or "").strip(),
                        "why_fit": (why.value or "").strip(),
                    },
                }
                with SessionFactory() as sdb:
                    sub, msg = submit_intake(sdb, token, payload)
                if not sub:
                    status.set_text(msg)
                    ui.notify(msg, type="warning")
                    return
                ui.notify("Submitted — thank you!", type="positive")
                ui.navigate.to(f"/intake/{token}")

            ui.button("Submit form", icon="send", on_click=do_submit).classes(
                "w-full bg-teal-600 hover:bg-teal-500 text-white font-semibold py-3 rounded-lg"
            )
            ui.label(
                "Your answers go to the recruiter for review before anything is saved permanently."
            ).classes("text-[11px] text-slate-500 text-center")

        _shell(body)


def intake_page(token: str):
    """Public route entry — no create_layout / Copilot."""
    render_intake_form(token)
