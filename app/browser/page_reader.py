"""Open a live browser page, expand collapsible sections, and extract readable text.

Uses Playwright (already a project dependency). Prefer this over thin search-snippet crawls
when you need experience, title, and summary from a real profile page.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("talenthunt.browser.page_reader")

# Buttons / controls that hide extra profile text
_EXPAND_SELECTORS = [
    'button:has-text("see more")',
    'button:has-text("See more")',
    'button:has-text("Show more")',
    'button:has-text("show more")',
    'button:has-text("View more")',
    'button:has-text("Read more")',
    'button:has-text("…see more")',
    'button:has-text("…more")',
    '[aria-expanded="false"]',
    'button.inline-show-more-text__button',
    'button[aria-label*="more" i]',
    'a:has-text("see more")',
    'span:has-text("see more")',
]

_LOGIN_WALL_HINTS = (
    "sign in",
    "join now",
    "log in",
    "login",
    "authwall",
    "challenge",
    "captcha",
    "verify you are a human",
    "session redirected",
)


def _cookies_from_db_session(platform: str) -> Optional[List[Dict[str, Any]]]:
    """Load cookies from the latest active BrowserSession for a platform, if any."""
    try:
        from app.infrastructure.db import SessionFactory
        from app.communications.service import list_browser_sessions

        with SessionFactory() as db:
            sessions = list_browser_sessions(db, platform=platform)
            for sess in sessions:
                if not sess.is_active or not sess.cookies_json:
                    continue
                raw = json.loads(sess.cookies_json)
                if isinstance(raw, list) and raw:
                    return raw
                if isinstance(raw, dict) and "cookies" in raw:
                    return raw["cookies"]
    except Exception as exc:
        logger.debug("No browser session cookies for %s: %s", platform, exc)
    return None


def _detect_platform(url: str) -> str:
    low = (url or "").lower()
    if "linkedin.com" in low:
        return "linkedin"
    if "naukri.com" in low:
        return "naukri"
    if "github.com" in low:
        return "github"
    return "web"


def _looks_blocked(title: str, text: str, url: str) -> bool:
    hay = f"{title} {text} {url}".lower()
    if any(h in hay for h in _LOGIN_WALL_HINTS) and len(text.strip()) < 800:
        return True
    if "linkedin.com/authwall" in hay or "/login" in (url or "").lower():
        return True
    return False


def _expand_collapsibles(page, max_clicks: int = 25) -> int:
    """Click common expand/show-more controls. Returns how many were clicked."""
    clicked = 0
    for _ in range(max_clicks):
        progressed = False
        for sel in _EXPAND_SELECTORS:
            try:
                loc = page.locator(sel)
                count = min(loc.count(), 6)
                for i in range(count):
                    el = loc.nth(i)
                    try:
                        if not el.is_visible():
                            continue
                        el.click(timeout=1200)
                        clicked += 1
                        progressed = True
                        page.wait_for_timeout(250)
                    except Exception:
                        continue
            except Exception:
                continue
        if not progressed:
            break
    return clicked


def _scroll_page(page, steps: int = 8) -> None:
    for i in range(steps):
        page.evaluate("window.scrollBy(0, Math.floor(window.innerHeight * 0.85))")
        page.wait_for_timeout(200)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(150)


def open_page_and_read(
    url: str,
    *,
    headless: bool = True,
    timeout_ms: int = 45000,
    use_saved_cookies: bool = True,
) -> Dict[str, Any]:
    """Open URL in Chromium, expand sections, return full page text + metadata.

    Always runs Playwright Sync API in a worker thread so it is safe when the
    caller sits on an asyncio / NiceGUI event loop.
    """
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(
            _open_page_and_read_sync,
            url,
            headless=headless,
            timeout_ms=timeout_ms,
            use_saved_cookies=use_saved_cookies,
        )
        return fut.result(timeout=max(90, (timeout_ms // 1000) + 45))


def _open_page_and_read_sync(
    url: str,
    *,
    headless: bool = True,
    timeout_ms: int = 45000,
    use_saved_cookies: bool = True,
) -> Dict[str, Any]:
    """Open URL in Chromium, expand sections, return full page text + metadata."""
    target = (url or "").strip()
    if not target:
        return {"status": "error", "error": "Empty URL", "text": ""}
    if not target.startswith(("http://", "https://")):
        target = "https://" + target

    platform = _detect_platform(target)
    cookies = _cookies_from_db_session(platform) if use_saved_cookies else None

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        return {"status": "error", "error": f"Playwright not installed: {exc}", "text": ""}

    result: Dict[str, Any] = {
        "status": "error",
        "url": target,
        "final_url": target,
        "title": "",
        "text": "",
        "expanded_clicks": 0,
        "blocked": False,
        "platform": platform,
        "error": None,
    }

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(
                viewport={"width": 1365, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                locale="en-IN",
            )
            if cookies:
                try:
                    # Normalize cookie dicts for Playwright
                    normalized = []
                    for c in cookies:
                        if not isinstance(c, dict) or "name" not in c or "value" not in c:
                            continue
                        item = {
                            "name": c["name"],
                            "value": c["value"],
                            "domain": c.get("domain") or c.get("Domain") or ".linkedin.com",
                            "path": c.get("path") or "/",
                        }
                        if "expires" in c:
                            item["expires"] = c["expires"]
                        if "httpOnly" in c:
                            item["httpOnly"] = c["httpOnly"]
                        if "secure" in c:
                            item["secure"] = c["secure"]
                        normalized.append(item)
                    if normalized:
                        context.add_cookies(normalized)
                except Exception as cookie_exc:
                    logger.warning("Could not apply saved cookies: %s", cookie_exc)

            page = context.new_page()
            page.goto(target, wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                page.wait_for_load_state("networkidle", timeout=min(12000, timeout_ms))
            except Exception:
                pass

            _scroll_page(page)
            expanded = _expand_collapsibles(page)
            _scroll_page(page, steps=4)
            expanded += _expand_collapsibles(page, max_clicks=10)

            title = page.title() or ""
            final_url = page.url or target

            # Prefer main/article text; fall back to body
            text = ""
            for sel in ("main", "article", "#main", "body"):
                try:
                    if page.locator(sel).count():
                        text = page.locator(sel).first.inner_text(timeout=5000) or ""
                        if len(text.strip()) > 200:
                            break
                except Exception:
                    continue

            # Accessibility tree as a secondary structured snapshot (names/roles)
            a11y_bits: List[str] = []
            try:
                snap = page.accessibility.snapshot()
                if snap:
                    def _walk(node, depth=0):
                        if not isinstance(node, dict) or depth > 12:
                            return
                        name = (node.get("name") or "").strip()
                        role = (node.get("role") or "").strip()
                        if name and role not in {"none", "generic", "InlineTextBox"}:
                            if len(name) > 1:
                                a11y_bits.append(name)
                        for child in node.get("children") or []:
                            _walk(child, depth + 1)
                    _walk(snap)
            except Exception:
                pass

            if a11y_bits and len(" ".join(a11y_bits)) > len(text) * 0.6:
                # Merge unique a11y lines that add signal
                extra = "\n".join(dict.fromkeys(a11y_bits))
                text = (text + "\n\n" + extra).strip()

            text = re.sub(r"\n{3,}", "\n\n", text).strip()
            blocked = _looks_blocked(title, text, final_url)

            result.update({
                "status": "blocked" if blocked else "success",
                "final_url": final_url,
                "title": title,
                "text": text,
                "expanded_clicks": expanded,
                "blocked": blocked,
                "error": "Login/auth wall detected — save a Browser Session with cookies, or open while logged in."
                if blocked else None,
            })
            context.close()
            browser.close()
    except Exception as exc:
        logger.error("open_page_and_read failed for %s: %s", target, exc)
        result["error"] = str(exc)
        result["status"] = "error"

    return result


def enrich_profile_from_url(url: str, **kwargs) -> Dict[str, Any]:
    """Read a profile page and pull lightweight fields for TalentHunt matching."""
    from app.hunts.experience import estimate_years_from_text, title_implies_seniority

    raw = open_page_and_read(url, **kwargs)
    text = raw.get("text") or ""
    title = raw.get("title") or ""

    # Heuristic headline: first substantial line that is not the site chrome
    headline = ""
    for line in text.splitlines():
        line = line.strip()
        if len(line) < 8 or len(line) > 140:
            continue
        low = line.lower()
        if any(x in low for x in ("linkedin", "naukri", "cookie", "skip to", "home")):
            continue
        headline = line
        break

    years = estimate_years_from_text(text, title)
    return {
        **raw,
        "headline": headline,
        "experience_years": years,
        "senior_title": title_implies_seniority(headline) or title_implies_seniority(title),
        "summary": text[:1200] if text else "",
    }
