"""Warm, bounded Playwright browser pool for profile reads."""

from __future__ import annotations

import asyncio
import atexit
import concurrent.futures
import hashlib
import json
import logging
import threading
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit

logger = logging.getLogger("talenthunt.browser.profile_pool")

_EXPAND_SELECTORS = (
    'button:has-text("see more")',
    'button:has-text("See more")',
    'button:has-text("Show more")',
    'button:has-text("show more")',
    'button:has-text("View more")',
    'button:has-text("Read more")',
    '[aria-expanded="false"]',
    'button.inline-show-more-text__button',
    'button[aria-label*="more" i]',
)


def normalize_cookies(cookies: Optional[List[Dict[str, Any]]], platform: str) -> List[Dict[str, Any]]:
    """Normalize stored browser cookies to Playwright's accepted shape."""
    default_domains = {
        "linkedin": ".linkedin.com",
        "naukri": ".naukri.com",
        "github": ".github.com",
    }
    normalized: List[Dict[str, Any]] = []
    for cookie in cookies or []:
        if not isinstance(cookie, dict) or "name" not in cookie or "value" not in cookie:
            continue
        item: Dict[str, Any] = {
            "name": str(cookie["name"]),
            "value": str(cookie["value"]),
            "domain": cookie.get("domain") or cookie.get("Domain") or default_domains.get(platform, ""),
            "path": cookie.get("path") or "/",
        }
        if not item["domain"]:
            continue
        for key in ("httpOnly", "secure"):
            if key in cookie:
                item[key] = bool(cookie[key])
        if cookie.get("expires") is not None:
            try:
                item["expires"] = float(cookie["expires"])
            except (TypeError, ValueError):
                pass
        same_site = str(cookie.get("sameSite") or "").capitalize()
        if same_site in {"Strict", "Lax", "None"}:
            item["sameSite"] = same_site
        normalized.append(item)
    return normalized


def _cookie_fingerprint(cookies: List[Dict[str, Any]]) -> str:
    payload = json.dumps(cookies, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ProfileBrowserPool:
    """Own one async Chromium process and reusable authenticated contexts.

    The NiceGUI sourcing path is synchronous inside a background worker. Calls are
    bridged onto this pool's dedicated asyncio loop, keeping Playwright objects on
    one thread while avoiding a Chromium launch for every candidate.
    """

    def __init__(self, max_pages: int = 2) -> None:
        self.max_pages = max(1, int(max_pages))
        self._start_lock = threading.Lock()
        self._ready = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._playwright = None
        self._browser = None
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._browser_lock: Optional[asyncio.Lock] = None
        self._context_lock: Optional[asyncio.Lock] = None
        self._contexts: Dict[str, Tuple[str, Any]] = {}

    def read(
        self,
        url: str,
        *,
        platform: str,
        cookies: Optional[List[Dict[str, Any]]] = None,
        timeout_ms: int = 45_000,
        save_snapshot: bool = False,
        scan_mode: bool = False,
    ) -> Dict[str, Any]:
        self._ensure_thread()
        if not self._loop:
            raise RuntimeError("Profile browser event loop did not start")
        future = asyncio.run_coroutine_threadsafe(
            self._read_async(
                url,
                platform=platform,
                cookies=cookies,
                timeout_ms=timeout_ms,
                save_snapshot=save_snapshot,
                scan_mode=scan_mode,
            ),
            self._loop,
        )
        wait_sec = max(5.0, (timeout_ms / 1000.0) + 8.0)
        try:
            return future.result(timeout=wait_sec)
        except concurrent.futures.TimeoutError as exc:
            future.cancel()
            raise TimeoutError(f"Profile page timed out after {wait_sec:.0f}s") from exc

    def _ensure_thread(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        with self._start_lock:
            if self._thread and self._thread.is_alive():
                return
            self._ready.clear()
            self._thread = threading.Thread(
                target=self._thread_main,
                name="profile-browser-pool",
                daemon=True,
            )
            self._thread.start()
            if not self._ready.wait(timeout=10):
                raise RuntimeError("Timed out starting profile browser pool")

    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._ready.set()
        try:
            loop.run_forever()
        finally:
            try:
                loop.run_until_complete(self._shutdown_async())
            except Exception:
                logger.debug("Profile browser shutdown failed", exc_info=True)
            loop.close()

    async def _ensure_browser(self) -> None:
        if self._browser and self._browser.is_connected():
            return
        if self._browser_lock is None:
            self._browser_lock = asyncio.Lock()
        async with self._browser_lock:
            if self._browser and self._browser.is_connected():
                return
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
            self._semaphore = asyncio.Semaphore(self.max_pages)
            self._context_lock = asyncio.Lock()

    async def _get_context(
        self,
        platform: str,
        cookies: Optional[List[Dict[str, Any]]],
        *,
        scan_mode: bool,
    ):
        await self._ensure_browser()
        normalized = normalize_cookies(cookies, platform)
        fingerprint = _cookie_fingerprint(normalized)
        context_key = f"{platform}:{'scan' if scan_mode else 'capture'}"
        assert self._context_lock is not None
        async with self._context_lock:
            cached = self._contexts.get(context_key)
            if cached and cached[0] == fingerprint:
                return cached[1]
            if cached:
                try:
                    await cached[1].close()
                except Exception:
                    logger.debug("Could not close stale %s context", context_key, exc_info=True)

            context = await self._browser.new_context(
                viewport={"width": 1365, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                locale="en-IN",
            )
            if scan_mode:
                async def _route(route, request) -> None:
                    if request.resource_type in {"image", "font", "media"}:
                        await route.abort()
                    else:
                        await route.continue_()

                await context.route("**/*", _route)
            if normalized:
                await context.add_cookies(normalized)
            self._contexts[context_key] = (fingerprint, context)
            return context

    async def _read_async(
        self,
        url: str,
        *,
        platform: str,
        cookies: Optional[List[Dict[str, Any]]],
        timeout_ms: int,
        save_snapshot: bool,
        scan_mode: bool,
    ) -> Dict[str, Any]:
        await self._ensure_browser()
        assert self._semaphore is not None
        async with self._semaphore:
            context = await self._get_context(platform, cookies, scan_mode=scan_mode)
            page = await context.new_page()
            try:
                page.set_default_timeout(min(timeout_ms, 5_000))
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                try:
                    await page.wait_for_load_state(
                        "networkidle",
                        timeout=min(2_000 if scan_mode else 7_000, timeout_ms),
                    )
                except Exception:
                    pass

                await self._scroll(page, 3 if scan_mode else 8)
                expanded = await self._expand(page, 6 if scan_mode else 25)
                await self._scroll(page, 2 if scan_mode else 4)
                expanded += await self._expand(page, 2 if scan_mode else 10)

                title = await page.title() or ""
                text = ""
                for selector in ("main", "article", "#main", "body"):
                    try:
                        locator = page.locator(selector).first
                        if await locator.count():
                            text = await locator.inner_text(
                                timeout=2_500 if scan_mode else 5_000
                            ) or ""
                            if len(text.strip()) > 200:
                                break
                    except Exception:
                        continue

                profile_image_url = ""
                contact_text = ""
                if platform == "linkedin":
                    try:
                        from app.browser.page_reader import _PROFILE_IMAGE_JS

                        profile_image_url = await page.evaluate(_PROFILE_IMAGE_JS) or ""
                    except Exception:
                        pass
                    for selector in ('a[href*="contact-info"]', 'a:has-text("Contact info")'):
                        try:
                            link = page.locator(selector).first
                            if not await link.count() or not await link.is_visible():
                                continue
                            await link.click(timeout=1_500)
                            await page.wait_for_timeout(500)
                            dialog = page.locator('[role="dialog"]').last
                            if await dialog.count():
                                contact_text = (await dialog.inner_text(timeout=2_000) or "").strip()
                                await page.keyboard.press("Escape")
                                break
                        except Exception:
                            continue
                    if contact_text:
                        text = f"{text}\n\nContact info\n{contact_text}".strip()

                html = await page.content() if save_snapshot else ""
                screenshot = None
                if save_snapshot:
                    try:
                        screenshot = await page.screenshot(full_page=True, type="png")
                    except Exception:
                        logger.warning("Profile screenshot failed for %s", url, exc_info=True)
                if platform == "linkedin" and not scan_mode:
                    details = await self._read_linkedin_detail_sections(
                        context,
                        page.url or url,
                        timeout_ms=min(timeout_ms, 10_000),
                    )
                    if details:
                        text = f"{text}\n\n{details}".strip()
                return {
                    "status": "success",
                    "final_url": page.url or url,
                    "title": title,
                    "text": text,
                    "expanded_clicks": expanded,
                    "html": html,
                    "screenshot_bytes": screenshot,
                    "profile_image_url": profile_image_url,
                    "contact_text": contact_text,
                }
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Pooled profile read failed for %s: %s", url, exc)
                return {
                    "status": "error",
                    "final_url": page.url or url,
                    "title": "",
                    "text": "",
                    "expanded_clicks": 0,
                    "html": "",
                    "screenshot_bytes": None,
                    "error": str(exc),
                }
            finally:
                await page.close()

    @staticmethod
    async def _scroll(page, steps: int) -> None:
        for _ in range(steps):
            await page.evaluate("window.scrollBy(0, Math.floor(window.innerHeight * 0.85))")
            await page.wait_for_timeout(150)
        await page.evaluate("window.scrollTo(0, 0)")
        await page.wait_for_timeout(100)

    @staticmethod
    async def _read_linkedin_detail_sections(context, profile_url: str, *, timeout_ms: int) -> str:
        """Read LinkedIn's complete Experience, Education, and Skills detail pages."""
        parts = urlsplit(profile_url)
        path = parts.path.split("/details/", 1)[0].rstrip("/")
        if "/in/" not in path:
            return ""
        base = urlunsplit((parts.scheme, parts.netloc, path, "", ""))
        sections: list[str] = []
        for label, suffix in (
            ("Experience", "experience"),
            ("Education", "education"),
            ("Skills", "skills"),
        ):
            detail_page = await context.new_page()
            try:
                await detail_page.goto(
                    f"{base}/details/{suffix}/",
                    wait_until="domcontentloaded",
                    timeout=timeout_ms,
                )
                await detail_page.wait_for_timeout(500)
                await ProfileBrowserPool._scroll(detail_page, 4)
                await ProfileBrowserPool._expand(detail_page, 10)
                main = detail_page.locator("main").first
                section_text = (
                    await main.inner_text(timeout=3_000)
                    if await main.count()
                    else ""
                )
                if len((section_text or "").strip()) > 30:
                    sections.append(f"LinkedIn {label} details\n{section_text.strip()}")
            except Exception as exc:
                logger.debug("LinkedIn %s detail read failed: %s", label, exc)
            finally:
                await detail_page.close()
        return "\n\n".join(sections)

    @staticmethod
    async def _expand(page, max_clicks: int) -> int:
        clicked = 0
        while clicked < max(0, max_clicks):
            progressed = False
            for selector in _EXPAND_SELECTORS:
                if clicked >= max_clicks:
                    break
                try:
                    locator = page.locator(selector)
                    count = min(await locator.count(), 6, max_clicks - clicked)
                    for index in range(count):
                        element = locator.nth(index)
                        if not await element.is_visible():
                            continue
                        try:
                            await element.click(timeout=900)
                            clicked += 1
                            progressed = True
                            await page.wait_for_timeout(150)
                        except Exception:
                            continue
                except Exception:
                    continue
            if not progressed:
                break
        return clicked

    async def _shutdown_async(self) -> None:
        for _, context in list(self._contexts.values()):
            try:
                await context.close()
            except Exception:
                pass
        self._contexts.clear()
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    def close(self) -> None:
        loop = self._loop
        thread = self._thread
        if not loop or not thread or not thread.is_alive():
            return
        try:
            future = asyncio.run_coroutine_threadsafe(self._shutdown_async(), loop)
            future.result(timeout=8)
        except Exception:
            logger.debug("Timed out closing profile browser pool", exc_info=True)
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=3)
        self._thread = None
        self._loop = None


_POOL = ProfileBrowserPool(max_pages=2)
atexit.register(_POOL.close)


def get_profile_browser_pool() -> ProfileBrowserPool:
    return _POOL
