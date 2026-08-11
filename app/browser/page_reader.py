"""Open a live browser page, expand collapsible sections, and extract readable text.

Uses Playwright (already a project dependency). Prefer this over thin search-snippet crawls
when you need experience, title, and summary from a real profile page.
"""

from __future__ import annotations

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

_PROFILE_IMAGE_JS = """() => {
  const images = Array.from(document.querySelectorAll('main img, #main img'));
  const candidates = images.map((img) => {
    const rect = img.getBoundingClientRect();
    return {
      src: img.currentSrc || img.src || '',
      alt: img.alt || '',
      width: rect.width || img.naturalWidth || 0,
      height: rect.height || img.naturalHeight || 0,
    };
  }).filter((item) => item.src.startsWith('http') && item.width >= 80 && item.height >= 80);
  candidates.sort((a, b) => (b.width * b.height) - (a.width * a.height));
  return candidates.length ? candidates[0].src : '';
}"""


def _read_linkedin_contact_sync(page) -> str:
    """Open LinkedIn's contact overlay long enough to capture its visible text."""
    for selector in ('a[href*="contact-info"]', 'a:has-text("Contact info")'):
        try:
            link = page.locator(selector).first
            if not link.count() or not link.is_visible():
                continue
            link.click(timeout=1500)
            page.wait_for_timeout(500)
            dialog = page.locator('[role="dialog"]').last
            if dialog.count():
                contact = (dialog.inner_text(timeout=2000) or "").strip()
                page.keyboard.press("Escape")
                return contact
        except Exception:
            continue
    return ""


def _cookies_from_db_session(platform: str) -> Optional[List[Dict[str, Any]]]:
    """Load decrypted cookies from the latest active BrowserSession for a platform."""
    try:
        from app.infrastructure.db import SessionFactory
        from app.communications.service import get_decrypted_cookies_for_platform

        with SessionFactory() as db:
            cookies = get_decrypted_cookies_for_platform(db, platform)
            if cookies:
                return cookies
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
    while clicked < max(0, max_clicks):
        progressed = False
        for sel in _EXPAND_SELECTORS:
            if clicked >= max_clicks:
                break
            try:
                loc = page.locator(sel)
                count = min(loc.count(), 6, max_clicks - clicked)
                for i in range(count):
                    if clicked >= max_clicks:
                        break
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
    save_snapshot: bool = True,
    candidate_id: Optional[int] = None,
    scan_mode: bool = False,
    cookies: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Open URL in Chromium, expand sections, return text + optional local snapshot.

    Headless reads use the warm async pool. Visible reads retain the isolated
    sync worker used by interactive/manual workflows.
    """
    if headless:
        return _open_page_and_read_pooled(
            url,
            timeout_ms=timeout_ms,
            use_saved_cookies=use_saved_cookies,
            save_snapshot=save_snapshot,
            candidate_id=candidate_id,
            scan_mode=scan_mode,
            cookies=cookies,
        )

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(
            _open_page_and_read_sync,
            url,
            headless=headless,
            timeout_ms=timeout_ms,
            use_saved_cookies=use_saved_cookies,
            save_snapshot=save_snapshot,
            candidate_id=candidate_id,
            scan_mode=scan_mode,
            cookies=cookies,
        )
        return fut.result(timeout=max(90, (timeout_ms // 1000) + 45))


def _open_page_and_read_pooled(
    url: str,
    *,
    timeout_ms: int,
    use_saved_cookies: bool,
    save_snapshot: bool,
    candidate_id: Optional[int],
    scan_mode: bool,
    cookies: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Read a page through the warm async browser and persist optional evidence."""
    target = (url or "").strip()
    if not target:
        return {"status": "error", "error": "Empty URL", "text": ""}
    if not target.startswith(("http://", "https://")):
        target = "https://" + target

    platform = _detect_platform(target)
    saved_cookies = cookies
    if use_saved_cookies and saved_cookies is None:
        saved_cookies = _cookies_from_db_session(platform)

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
        "snapshot": None,
    }
    try:
        from app.browser.profile_pool import get_profile_browser_pool

        raw = get_profile_browser_pool().read(
            target,
            platform=platform,
            cookies=saved_cookies,
            timeout_ms=timeout_ms,
            save_snapshot=save_snapshot,
            scan_mode=scan_mode,
        )
        if raw.get("status") != "success":
            result.update(raw)
            return result

        title = raw.get("title") or ""
        text = re.sub(r"\n{3,}", "\n\n", raw.get("text") or "").strip()
        final_url = raw.get("final_url") or target
        blocked = _looks_blocked(title, text, final_url)
        snapshot_info = None
        if save_snapshot and not blocked and text:
            from app.browser.snapshots import snapshot_dir_for, write_snapshot_files

            out = snapshot_dir_for(url=final_url, candidate_id=candidate_id)
            snapshot_info = write_snapshot_files(
                out,
                url=target,
                final_url=final_url,
                title=title,
                text=text,
                html=raw.get("html") or "",
                screenshot_bytes=raw.get("screenshot_bytes"),
                extra_meta={"platform": platform, "candidate_id": candidate_id},
            )
            snapshot_info["url"] = target
            if candidate_id:
                from app.browser.snapshots import register_snapshot_record

                register_snapshot_record(candidate_id=int(candidate_id), snapshot_info=snapshot_info)

        result.update({
            "status": "blocked" if blocked else "success",
            "final_url": final_url,
            "title": title,
            "text": text,
            "expanded_clicks": raw.get("expanded_clicks") or 0,
            "blocked": blocked,
            "profile_image_url": raw.get("profile_image_url") or "",
            "contact_text": raw.get("contact_text") or "",
            "snapshot": snapshot_info,
            "error": (
                "Login/auth wall detected - connect this site under Settings > Connected sites, then retry."
                if blocked else None
            ),
        })
    except Exception as exc:
        logger.error("Pooled page read failed for %s: %s", target, exc)
        result["error"] = str(exc)
    return result


def _open_page_and_read_sync(
    url: str,
    *,
    headless: bool = True,
    timeout_ms: int = 45000,
    use_saved_cookies: bool = True,
    save_snapshot: bool = True,
    candidate_id: Optional[int] = None,
    scan_mode: bool = False,
    cookies: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Open URL in Chromium, expand sections, return full page text + metadata."""
    target = (url or "").strip()
    if not target:
        return {"status": "error", "error": "Empty URL", "text": ""}
    if not target.startswith(("http://", "https://")):
        target = "https://" + target

    platform = _detect_platform(target)
    if use_saved_cookies and cookies is None:
        cookies = _cookies_from_db_session(platform)

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
        "snapshot": None,
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
                settle_ms = 2000 if scan_mode else 12000
                page.wait_for_load_state("networkidle", timeout=min(settle_ms, timeout_ms))
            except Exception:
                pass

            _scroll_page(page, steps=3 if scan_mode else 8)
            expanded = _expand_collapsibles(page, max_clicks=6 if scan_mode else 25)
            _scroll_page(page, steps=2 if scan_mode else 4)
            expanded += _expand_collapsibles(page, max_clicks=2 if scan_mode else 10)

            title = page.title() or ""
            final_url = page.url or target

            # Prefer main/article text; fall back to body
            text = ""
            for sel in ("main", "article", "#main", "body"):
                try:
                    if page.locator(sel).count():
                        text = page.locator(sel).first.inner_text(
                            timeout=2500 if scan_mode else 5000
                        ) or ""
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
            profile_image_url = ""
            contact_text = ""
            if platform == "linkedin":
                try:
                    profile_image_url = page.evaluate(_PROFILE_IMAGE_JS) or ""
                except Exception:
                    pass
                contact_text = _read_linkedin_contact_sync(page)
                if contact_text:
                    text = f"{text}\n\nContact info\n{contact_text}".strip()
            blocked = _looks_blocked(title, text, final_url)

            snapshot_info = None
            if save_snapshot and not blocked and text:
                try:
                    from app.browser.snapshots import snapshot_dir_for, write_snapshot_files

                    html = ""
                    try:
                        html = page.content() or ""
                    except Exception:
                        html = ""
                    shot = None
                    try:
                        shot = page.screenshot(full_page=True, type="png")
                    except Exception as shot_exc:
                        logger.warning("screenshot failed: %s", shot_exc)
                    out = snapshot_dir_for(url=final_url or target, candidate_id=candidate_id)
                    snapshot_info = write_snapshot_files(
                        out,
                        url=target,
                        final_url=final_url,
                        title=title,
                        text=text,
                        html=html,
                        screenshot_bytes=shot,
                        extra_meta={"platform": platform, "candidate_id": candidate_id},
                    )
                    snapshot_info["url"] = target
                    logger.info(
                        "[snapshot] saved %s chars=%s shot=%s",
                        snapshot_info.get("snapshot_dir"),
                        len(text),
                        bool(shot),
                    )
                except Exception as snap_exc:
                    logger.warning("Failed to save profile snapshot: %s", snap_exc)

            if snapshot_info and candidate_id:
                try:
                    from app.browser.snapshots import register_snapshot_record

                    snapshot_info["url"] = target
                    register_snapshot_record(
                        candidate_id=int(candidate_id),
                        snapshot_info=snapshot_info,
                    )
                except Exception as reg_exc:
                    logger.warning("Failed to register snapshot for candidate %s: %s", candidate_id, reg_exc)

            result.update({
                "status": "blocked" if blocked else "success",
                "final_url": final_url,
                "title": title,
                "text": text,
                "expanded_clicks": expanded,
                "blocked": blocked,
                "profile_image_url": profile_image_url,
                "contact_text": contact_text,
                "snapshot": snapshot_info,
                "error": "Login/auth wall detected — connect this site under Settings → Connected sites, then retry."
                if blocked else None,
            })
            context.close()
            browser.close()
    except Exception as exc:
        logger.error("open_page_and_read failed for %s: %s", target, exc)
        result["error"] = str(exc)
        result["status"] = "error"

    return result


def enrich_profile_from_url(
    url: str,
    *,
    candidate_id: Optional[int] = None,
    save_snapshot: bool = True,
    **kwargs,
) -> Dict[str, Any]:
    """Read a profile page, save a local snapshot (free/Playwright), pull fields."""
    from app.hunts.experience import estimate_years_from_text, title_implies_seniority
    from app.hunts.location import extract_location_from_text, linkedin_host_country

    raw = open_page_and_read(
        url,
        candidate_id=candidate_id,
        save_snapshot=save_snapshot,
        **kwargs,
    )
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
    location = extract_location_from_text(text, title) or linkedin_host_country(url)
    return {
        **raw,
        "headline": headline,
        "experience_years": years,
        "location": location,
        "senior_title": title_implies_seniority(headline) or title_implies_seniority(title),
        "summary": text[:1200] if text else "",
        "profile_image_url": raw.get("profile_image_url") or "",
        "contact_text": raw.get("contact_text") or "",
    }
