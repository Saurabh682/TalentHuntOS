"""Interactive site login via headed Playwright — save encrypted cookies locally.

Free/local only. User logs in themselves; we never store passwords.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("talenthunt.browser.session_auth")

PLATFORM_LOGIN: Dict[str, Dict[str, Any]] = {
    "linkedin": {
        "label": "LinkedIn",
        "login_url": "https://www.linkedin.com/login",
        "home_url": "https://www.linkedin.com/feed/",
        # Strong auth cookie only — do not treat anonymous cookies as logged-in
        "required_cookies": ("li_at",),
        "success_url_bits": ("/feed", "/mynetwork", "/jobs"),
        "block_url_bits": ("/login", "/authwall", "/checkpoint", "/uas/login"),
        "logged_out_hints": ("sign in", "join now", "authwall", "session redirected"),
    },
    "naukri": {
        "label": "Naukri",
        "login_url": "https://www.naukri.com/nlogin/login",
        "home_url": "https://www.naukri.com/mnjuser/homepage",
        # naukWS alone can appear before a real login — require nauk_at + home URL
        "required_cookies": ("nauk_at",),
        "require_success_url": True,
        "success_url_bits": ("mnjuser", "/mnjuser/"),
        "block_url_bits": ("/nlogin", "/login"),
        "logged_out_hints": ("login to naukri", "register now", "nlogin", "otp"),
    },
    "github": {
        "label": "GitHub",
        "login_url": "https://github.com/login",
        "home_url": "https://github.com/",
        "required_cookies": ("user_session",),
        "success_url_bits": ("github.com/",),
        "block_url_bits": ("/login", "/session"),
        "logged_out_hints": ("sign in", "sign up"),
    },
    "indeed": {
        "label": "Indeed",
        "login_url": "https://secure.indeed.com/auth",
        "home_url": "https://www.indeed.com/",
        # Anonymous visitors also get CTK/PPID — never auto-detect; Save only after leaving /auth
        "required_cookies": (),
        "manual_save_only": True,
        "success_url_bits": ("indeed.com/",),
        "block_url_bits": ("/auth", "/account/login", "secure.indeed.com/auth"),
        "logged_out_hints": ("sign in", "create account"),
    },
}


def supported_platforms() -> List[Dict[str, str]]:
    return [
        {"id": k, "label": v["label"], "login_url": v["login_url"]}
        for k, v in PLATFORM_LOGIN.items()
    ]


def _cookie_names(cookies: List[Dict[str, Any]]) -> set:
    return {str(c.get("name") or "") for c in cookies if isinstance(c, dict)}


def _cookie_map(cookies: List[Dict[str, Any]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for c in cookies:
        if isinstance(c, dict) and c.get("name"):
            out[str(c["name"])] = str(c.get("value") or "")
    return out


def _has_required_cookies(platform: str, cookies: List[Dict[str, Any]]) -> bool:
    cfg = PLATFORM_LOGIN.get(platform) or {}
    required = tuple(cfg.get("required_cookies") or ())
    if not required:
        return False
    names = _cookie_names(cookies)
    cmap = _cookie_map(cookies)
    if platform == "github":
        if cmap.get("logged_in", "").lower() == "yes" and "user_session" in names:
            return True
        return "user_session" in names and bool(cmap.get("user_session"))
    if cfg.get("any_required_cookies"):
        return any(n in names and bool(cmap.get(n)) for n in required)
    return all(n in names and bool(cmap.get(n)) for n in required)


def _looks_logged_in(platform: str, url: str, cookies: List[Dict[str, Any]]) -> bool:
    """True only when strong auth cookies are present (and not stuck on a login URL)."""
    cfg = PLATFORM_LOGIN.get(platform) or {}
    low = (url or "").lower()
    block = tuple(cfg.get("block_url_bits") or ())
    if any(b in low for b in block):
        return False
    if cfg.get("manual_save_only"):
        return False
    if not _has_required_cookies(platform, cookies):
        return False
    if cfg.get("require_success_url"):
        bits = tuple(cfg.get("success_url_bits") or ())
        if bits and not any(b in low for b in bits):
            return False
    return True


def _accept_save(
    platform: str,
    url: str,
    cookies: List[Dict[str, Any]],
    *,
    force_save: bool,
) -> bool:
    cfg = PLATFORM_LOGIN.get(platform) or {}
    low = (url or "").lower()
    block = tuple(cfg.get("block_url_bits") or ())
    if any(b in low for b in block):
        return False
    if cfg.get("manual_save_only"):
        # Indeed: Save only after leaving auth, with a real cookie jar
        return bool(force_save) and len(cookies) >= 5
    # Never accept Save while still on login — even if force_save
    if not _looks_logged_in(platform, url, cookies):
        return False
    return True


def interactive_connect(
    platform: str,
    *,
    timeout_sec: int = 600,
    save_event: Optional[threading.Event] = None,
    cancel_event: Optional[threading.Event] = None,
    progress: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Open a visible Chromium window; wait for login; persist encrypted cookies.

    Runs Playwright Sync API — call from a worker thread (not the NiceGUI loop).
    ``progress`` (optional dict) gets ``message`` updates for the UI while waiting.
    """
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(
            _interactive_connect_sync,
            platform,
            timeout_sec=timeout_sec,
            save_event=save_event,
            cancel_event=cancel_event,
            progress=progress,
        )
        return fut.result(timeout=max(timeout_sec + 60, 120))


def _set_progress(progress: Optional[Dict[str, Any]], message: str) -> None:
    if progress is not None:
        progress["message"] = message


def _launch_visible_browser(playwright):
    """Prefer an installed browser, falling back to Playwright Chromium."""
    errors = []
    launch_args = {
        "headless": False,
        "args": ["--disable-blink-features=AutomationControlled"],
        "ignore_default_args": ["--enable-automation"],
    }
    for channel in ("msedge", "chrome", None):
        try:
            kwargs = dict(launch_args)
            if channel:
                kwargs["channel"] = channel
            return playwright.chromium.launch(**kwargs), channel or "chromium"
        except Exception as exc:
            errors.append(f"{channel or 'chromium'}: {exc}")
    raise RuntimeError("Could not launch a visible browser. " + " | ".join(errors))


def _interactive_connect_sync(
    platform: str,
    *,
    timeout_sec: int = 600,
    save_event: Optional[threading.Event] = None,
    cancel_event: Optional[threading.Event] = None,
    progress: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    plat = (platform or "").strip().lower()
    cfg = PLATFORM_LOGIN.get(plat)
    if not cfg:
        return {"status": "error", "error": f"Unsupported platform: {platform}"}

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        return {"status": "error", "error": f"Playwright not installed: {exc}"}

    save_event = save_event or threading.Event()
    cancel_event = cancel_event or threading.Event()
    result: Dict[str, Any] = {
        "status": "error",
        "platform": plat,
        "error": None,
        "session_id": None,
        "cookie_count": 0,
    }

    logger.info("[session_auth] Opening login window for %s", plat)
    _set_progress(progress, f"Chromium opening for {cfg['label']}…")
    try:
        with sync_playwright() as p:
            browser, browser_channel = _launch_visible_browser(p)
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                locale="en-IN",
            )
            page = context.new_page()
            if progress is not None:
                progress["window_open"] = True
                progress["browser_channel"] = browser_channel
            _set_progress(progress, f"{browser_channel.title()} opened. Loading {cfg['label']}…")
            try:
                page.goto(cfg["login_url"], wait_until="domcontentloaded", timeout=60000)
            except Exception as exc:
                result["status"] = "navigation_error"
                result["error"] = (
                    f"{browser_channel.title()} opened but could not reach {cfg['label']}: {exc}"
                )
                _set_progress(progress, result["error"])
                return result
            if progress is not None:
                progress["login_page_loaded"] = True
            _set_progress(
                progress,
                f"Log in to {cfg['label']} in {browser_channel.title()}. "
                "Only click Save session after you see your home/feed — not on the login form.",
            )

            deadline = time.time() + max(60, int(timeout_sec))
            saved = False
            while time.time() < deadline:
                if cancel_event.is_set():
                    result["status"] = "cancelled"
                    result["error"] = "Cancelled by user"
                    break

                cookies = context.cookies()
                url = page.url or ""
                force_save = save_event.is_set()
                auto_ready = _looks_logged_in(plat, url, cookies)

                # Auto-save only when clearly logged in (never on bare Save)
                if auto_ready and not force_save:
                    time.sleep(1.5)
                    cookies = context.cookies()
                    url = page.url or ""
                    if not _looks_logged_in(plat, url, cookies):
                        time.sleep(1.0)
                        continue
                    _set_progress(progress, "Login detected — verifying session…")
                    verify = _verify_with_context(context, plat, cfg)
                    if not verify.get("ok"):
                        _set_progress(
                            progress,
                            (verify.get("detail") or "Not verified yet")
                            + " — keep the Chromium window open and finish login.",
                        )
                        time.sleep(2.0)
                        continue
                    sess = _persist_cookies(
                        platform=plat,
                        cookies=context.cookies(),
                        target_url=page.url or cfg.get("home_url"),
                    )
                    if sess:
                        _set_session_verify_meta(
                            sess.get("id"),
                            ok=True,
                            final_url=verify.get("final_url") or page.url,
                            detail=verify.get("detail") or "Verified",
                        )
                        result.update({
                            "status": "success",
                            "session_id": sess.get("id"),
                            "cookie_count": len(context.cookies()),
                            "final_url": page.url,
                            "encrypted": True,
                            "verified": True,
                            "verify_detail": verify.get("detail"),
                        })
                        saved = True
                        _set_progress(progress, f"{cfg['label']} verified and saved.")
                    else:
                        result["error"] = "Failed to persist session to database"
                    break

                if force_save:
                    save_event.clear()
                    time.sleep(1.0)
                    cookies = context.cookies()
                    url = page.url or ""
                    if not _accept_save(plat, url, cookies, force_save=True):
                        msg = (
                            f"Still on login / missing auth cookie for {cfg['label']}. "
                            "Finish signing in until you see your home page, then Save again. "
                            "Chromium stays open."
                        )
                        result["error"] = msg
                        _set_progress(progress, msg)
                        logger.info("[session_auth] Save rejected — not ready url=%s", url[:100])
                        continue

                    _set_progress(progress, "Checking login before saving…")
                    verify = _verify_with_context(context, plat, cfg)
                    if not verify.get("ok"):
                        msg = (
                            (verify.get("detail") or "Login check failed")
                            + " — Chromium stays open. Finish login, then Save again."
                        )
                        result["error"] = msg
                        _set_progress(progress, msg)
                        logger.info("[session_auth] Save rejected — verify failed for %s", plat)
                        continue

                    sess = _persist_cookies(
                        platform=plat,
                        cookies=context.cookies(),
                        target_url=page.url or cfg.get("home_url"),
                    )
                    if sess:
                        _set_session_verify_meta(
                            sess.get("id"),
                            ok=True,
                            final_url=verify.get("final_url") or page.url,
                            detail=verify.get("detail") or "Verified",
                        )
                        result.update({
                            "status": "success",
                            "session_id": sess.get("id"),
                            "cookie_count": len(context.cookies()),
                            "final_url": page.url,
                            "encrypted": True,
                            "verified": True,
                            "verify_detail": verify.get("detail"),
                        })
                        saved = True
                        _set_progress(progress, f"{cfg['label']} verified and saved.")
                        logger.info(
                            "[session_auth] Saved+verified %s session id=%s cookies=%s",
                            plat,
                            sess.get("id"),
                            len(context.cookies()),
                        )
                    else:
                        result["error"] = "Failed to persist session to database"
                    break

                time.sleep(1.0)

            if not saved and result["status"] != "cancelled":
                if result.get("error") and "Save" in (result.get("error") or ""):
                    # Had a save rejection; treat as timeout only if we never saved
                    result["status"] = "timeout"
                else:
                    result["status"] = "timeout"
                    result["error"] = (
                        f"Timed out waiting for {cfg['label']} login. "
                        "Log in in Chromium until home/feed is visible, then Save session."
                    )

            try:
                browser.close()
            except Exception:
                pass
    except Exception as exc:
        logger.exception("interactive_connect failed for %s", plat)
        result["status"] = "launch_error"
        result["error"] = str(exc)

    return result


def _persist_cookies(
    *,
    platform: str,
    cookies: List[Dict[str, Any]],
    target_url: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    from app.infrastructure.db import SessionFactory
    from app.communications.service import upsert_browser_session_cookies

    clean: List[Dict[str, Any]] = []
    for c in cookies:
        if not isinstance(c, dict) or not c.get("name"):
            continue
        item = {
            "name": c["name"],
            "value": c.get("value", ""),
            "domain": c.get("domain") or "",
            "path": c.get("path") or "/",
        }
        for k in ("expires", "httpOnly", "secure", "sameSite"):
            if k in c and c[k] is not None:
                item[k] = c[k]
        clean.append(item)

    with SessionFactory() as db:
        row = upsert_browser_session_cookies(
            db,
            platform=platform,
            cookies=clean,
            target_url=target_url,
            session_name=f"{PLATFORM_LOGIN.get(platform, {}).get('label', platform)} (local)",
        )
        if not row:
            return None
        return {
            "id": row.id,
            "platform": row.platform,
            "session_name": row.session_name,
            "is_active": row.is_active,
        }


def _set_session_verify_meta(
    session_id: Optional[int],
    *,
    ok: bool,
    final_url: str = "",
    detail: str = "",
) -> None:
    if not session_id:
        return
    import json
    from datetime import datetime, timezone
    from app.infrastructure.db import SessionFactory
    from app.communications.service import get_browser_session

    with SessionFactory() as db:
        row = get_browser_session(db, int(session_id))
        if not row:
            return
        meta = {
            "verified": bool(ok),
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "final_url": (final_url or "")[:300],
            "detail": (detail or "")[:300],
        }
        row.headers_json = json.dumps(meta)
        if ok:
            row.last_accessed_at = datetime.now(timezone.utc)
        db.commit()


def _verify_with_context(context, platform: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Navigate to home with current context; decide if session looks authenticated."""
    try:
        page = context.new_page()
        page.goto(cfg.get("home_url") or cfg.get("login_url"), wait_until="domcontentloaded", timeout=45000)
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        final_url = page.url or ""
        text = ""
        try:
            text = (page.locator("body").inner_text(timeout=5000) or "")[:4000]
        except Exception:
            text = ""
        cookies = context.cookies()
        try:
            page.close()
        except Exception:
            pass
        return _evaluate_login_state(platform, final_url, text, cookies)
    except Exception as exc:
        return {"ok": False, "detail": str(exc), "final_url": ""}


def _evaluate_login_state(
    platform: str,
    url: str,
    text: str,
    cookies: List[Dict[str, Any]],
) -> Dict[str, Any]:
    cfg = PLATFORM_LOGIN.get(platform) or {}
    low_url = (url or "").lower()
    low_text = (text or "").lower()
    block = tuple(cfg.get("block_url_bits") or ())
    hints = tuple(cfg.get("logged_out_hints") or ())

    if any(b in low_url for b in block):
        return {
            "ok": False,
            "detail": "Landed on login/auth page — session is not logged in.",
            "final_url": url,
        }

    if not cfg.get("manual_save_only") and not _has_required_cookies(platform, cookies):
        return {
            "ok": False,
            "detail": "Missing auth cookie after open — reconnect and finish login.",
            "final_url": url,
        }

    # Soft text check (login walls)
    if hints and any(h in low_text for h in hints) and len(low_text) < 1500:
        return {
            "ok": False,
            "detail": "Page still looks logged-out.",
            "final_url": url,
        }

    return {
        "ok": True,
        "detail": "Opened home while authenticated.",
        "final_url": url,
    }


def verify_platform_session(platform: str, *, headless: bool = True) -> Dict[str, Any]:
    """Open the site with saved cookies and confirm the login still works."""
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(_verify_platform_session_sync, platform, headless=headless)
        return fut.result(timeout=90)


def _verify_platform_session_sync(platform: str, *, headless: bool = True) -> Dict[str, Any]:
    plat = (platform or "").strip().lower()
    cfg = PLATFORM_LOGIN.get(plat)
    if not cfg:
        return {"status": "error", "ok": False, "error": f"Unsupported platform: {platform}"}

    from app.infrastructure.db import SessionFactory
    from app.communications.service import get_decrypted_cookies_for_platform, list_browser_sessions

    with SessionFactory() as db:
        cookies = get_decrypted_cookies_for_platform(db, plat)
        sessions = [s for s in list_browser_sessions(db, platform=plat) if s.is_active and s.cookies_json]
        session_id = sessions[0].id if sessions else None

    if not cookies:
        return {
            "status": "disconnected",
            "ok": False,
            "platform": plat,
            "error": "No saved cookies — click Connect and log in.",
        }

    # Quick reject if strong cookie missing (skip live browser)
    if not cfg.get("manual_save_only") and not _has_required_cookies(plat, cookies):
        if session_id:
            _set_session_verify_meta(
                session_id,
                ok=False,
                detail="Saved cookies lack auth token (false connect). Reconnect.",
            )
        return {
            "status": "invalid",
            "ok": False,
            "platform": plat,
            "error": (
                "Saved session is not a real login (no auth cookie). "
                "Click Disconnect, then Connect, and sign in in the Chromium window."
            ),
        }

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        return {"status": "error", "ok": False, "error": str(exc)}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                locale="en-IN",
            )
            try:
                context.add_cookies(cookies)
            except Exception as cookie_exc:
                logger.warning("verify: could not apply cookies: %s", cookie_exc)

            verify = _verify_with_context(context, plat, cfg)
            browser.close()
    except Exception as exc:
        logger.exception("verify_platform_session failed")
        return {"status": "error", "ok": False, "platform": plat, "error": str(exc)}

    _set_session_verify_meta(
        session_id,
        ok=bool(verify.get("ok")),
        final_url=verify.get("final_url") or "",
        detail=verify.get("detail") or "",
    )

    if verify.get("ok"):
        return {
            "status": "verified",
            "ok": True,
            "platform": plat,
            "final_url": verify.get("final_url"),
            "detail": verify.get("detail"),
        }

    return {
        "status": "expired",
        "ok": False,
        "platform": plat,
        "final_url": verify.get("final_url"),
        "error": verify.get("detail") or "Session failed verification.",
    }


def get_platform_connection_status() -> List[Dict[str, Any]]:
    """UI-friendly status for each supported platform."""
    import json
    from app.infrastructure.db import SessionFactory, init_db
    from app.communications.service import list_browser_sessions, get_decrypted_cookies_for_platform
    from app.infrastructure.secret_box import is_sealed

    init_db()
    out: List[Dict[str, Any]] = []
    with SessionFactory() as db:
        sessions = list_browser_sessions(db)
        by_plat: Dict[str, Any] = {}
        for s in sessions:
            if not s.is_active:
                continue
            prev = by_plat.get(s.platform)
            if not prev or (s.last_accessed_at or s.created_at) > (
                prev.last_accessed_at or prev.created_at
            ):
                by_plat[s.platform] = s

        for plat, cfg in PLATFORM_LOGIN.items():
            sess = by_plat.get(plat)
            if not sess or not sess.cookies_json:
                out.append({
                    "platform": plat,
                    "label": cfg["label"],
                    "status": "disconnected",
                    "encrypted": False,
                    "verified": False,
                    "session_id": None,
                    "last_accessed_at": None,
                    "verify_detail": None,
                })
                continue

            meta: Dict[str, Any] = {}
            if sess.headers_json:
                try:
                    meta = json.loads(sess.headers_json) or {}
                except Exception:
                    meta = {}

            cookies = get_decrypted_cookies_for_platform(db, plat) or []
            has_auth = bool(cookies) and (
                cfg.get("manual_save_only") or _has_required_cookies(plat, cookies)
            )
            verified = bool(meta.get("verified")) and has_auth

            if not has_auth:
                status = "invalid"
            elif verified:
                status = "verified"
            else:
                status = "connected"  # cookies saved, not proven

            out.append({
                "platform": plat,
                "label": cfg["label"],
                "status": status,
                "encrypted": is_sealed(sess.cookies_json),
                "verified": verified,
                "session_id": sess.id,
                "session_name": sess.session_name,
                "last_accessed_at": sess.last_accessed_at.isoformat()
                if sess.last_accessed_at
                else (sess.created_at.isoformat() if sess.created_at else None),
                "verify_detail": meta.get("detail"),
                "verified_at": meta.get("verified_at"),
                "cookie_count": len(cookies),
            })
    return out


def disconnect_platform(platform: str, *, actor_type: str = "ui") -> Dict[str, Any]:
    from app.infrastructure.db import SessionFactory
    from app.communications.service import deactivate_browser_sessions_for_platform

    plat = (platform or "").strip().lower()
    with SessionFactory() as db:
        n = deactivate_browser_sessions_for_platform(db, plat, actor_type=actor_type)
    return {"status": "success", "platform": plat, "deactivated": n}
