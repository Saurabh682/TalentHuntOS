"""Run a local axe-core audit against TalentHunt OS with Playwright."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright

VIEWPORTS = {
    "desktop": {"width": 1440, "height": 900},
    "mobile": {"width": 390, "height": 844},
}
DEFAULT_ROUTES = [
    "/",
    "/hunts",
    "/discoveries",
    "/candidates",
    "/pipeline",
    "/playbook",
    "/communications",
    "/analytics",
    "/settings",
]


def _safe_name(route: str) -> str:
    value = route.strip("/") or "home"
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", value)


def _loopback_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise argparse.ArgumentTypeError("audit URL must use localhost or 127.0.0.1")
    return value.rstrip("/") + "/"


def _local_auth_cookie(base_url: str) -> dict[str, object] | None:
    """Create a short-lived local audit session without reading the administrator password."""
    from sqlalchemy import select

    from app.infrastructure.auth import SESSION_COOKIE, create_session_token
    from app.infrastructure.db import SessionFactory, User, init_db

    init_db()
    with SessionFactory() as db:
        username = db.scalar(
            select(User.username).where(User.role == "admin", User.is_active.is_(True)).limit(1)
        )
    if not username:
        return None
    return {
        "name": SESSION_COOKIE,
        "value": create_session_token(username),
        "url": base_url,
        "httpOnly": True,
        "sameSite": "Strict",
    }


async def run_audit(args: argparse.Namespace) -> int:
    root = Path(__file__).resolve().parents[1]
    axe_path = root / "node_modules" / "axe-core" / "axe.min.js"
    if not axe_path.exists():
        print("axe-core is missing; run 'npm install' in TalentHuntOS", file=sys.stderr)
        return 2

    output_dir = args.output.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    storage_state = str(args.storage_state.resolve()) if args.storage_state else None
    failures = 0
    auth_cookie = _local_auth_cookie(args.url) if args.authenticated else None
    if args.authenticated and auth_cookie is None:
        print(
            "No active local administrator is available for an authenticated audit.",
            file=sys.stderr,
        )
        return 2

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            for viewport_name, viewport in VIEWPORTS.items():
                context = await browser.new_context(viewport=viewport, storage_state=storage_state)
                if auth_cookie:
                    await context.add_cookies([auth_cookie])
                page = await context.new_page()
                audited_login = False
                try:
                    for route in args.routes:
                        await page.goto(
                            urljoin(args.url, route.lstrip("/")), wait_until="domcontentloaded"
                        )
                        await page.wait_for_timeout(args.settle_ms)
                        current_path = urlparse(page.url).path
                        is_login = current_path == "/login" or current_path.startswith("/auth/")
                        if is_login:
                            if audited_login:
                                break
                            audited_login = True
                            report_route = current_path
                        else:
                            report_route = route

                        await page.add_script_tag(path=str(axe_path))
                        result = await page.evaluate(
                            """async () => await axe.run(document, {
                                runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa']},
                                resultTypes: ['violations', 'incomplete']
                            })"""
                        )
                        layout = await page.evaluate(
                            """() => ({
                                viewportWidth: window.innerWidth,
                                documentWidth: Math.max(
                                    document.documentElement.scrollWidth,
                                    document.body ? document.body.scrollWidth : 0
                                )
                            })"""
                        )
                        layout["horizontalOverflow"] = (
                            layout["documentWidth"] > layout["viewportWidth"] + 1
                        )
                        result["talenthunt"] = {
                            "requestedUrl": urljoin(args.url, route.lstrip("/")),
                            "finalUrl": page.url,
                            "viewport": viewport,
                            "layout": layout,
                        }
                        report_path = (
                            output_dir / f"{viewport_name}-{_safe_name(report_route)}.json"
                        )
                        report_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
                        violations = result.get("violations", [])
                        route_failures = len(violations) + int(layout["horizontalOverflow"])
                        failures += route_failures
                        print(
                            f"{viewport_name} {report_route}: {len(violations)} violation(s), "
                            f"horizontal overflow={'yes' if layout['horizontalOverflow'] else 'no'}"
                        )
                        if is_login:
                            break
                finally:
                    await context.close()
        finally:
            await browser.close()

    if failures:
        print(f"Accessibility audit failed with {failures} violation(s).", file=sys.stderr)
        return 1
    print("Accessibility audit passed.")
    return 0


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", type=_loopback_url, default="http://127.0.0.1:8080/")
    parser.add_argument("--storage-state", type=Path)
    parser.add_argument("--authenticated", action="store_true")
    parser.add_argument("--settle-ms", type=int, default=750)
    parser.add_argument("--output", type=Path, default=root / "output" / "accessibility")
    parser.add_argument("routes", nargs="*", default=DEFAULT_ROUTES)
    args = parser.parse_args()
    return asyncio.run(run_audit(args))


if __name__ == "__main__":
    raise SystemExit(main())
