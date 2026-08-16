"""Local free profile page snapshots (Playwright PNG + text + HTML).

No paid scraping APIs — files live under ``data/profile_snapshots/``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config.settings import DATA_DIR

logger = logging.getLogger("talenthunt.browser.snapshots")

SNAPSHOTS_ROOT = DATA_DIR / "profile_snapshots"


def _safe_slug(text: str, max_len: int = 48) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", (text or "").strip())[:max_len].strip("-")
    return s or "unknown"


def url_key(url: str) -> str:
    raw = (url or "").strip().lower().split("?")[0].rstrip("/")
    return hashlib.sha1(raw.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]


def snapshot_dir_for(*, url: str, candidate_id: Optional[int] = None) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if candidate_id:
        base = SNAPSHOTS_ROOT / f"cand_{int(candidate_id)}" / ts
    else:
        base = SNAPSHOTS_ROOT / "by_url" / url_key(url) / ts
    base.mkdir(parents=True, exist_ok=True)
    return base


def write_snapshot_files(
    out_dir: Path,
    *,
    url: str,
    final_url: str = "",
    title: str = "",
    text: str = "",
    html: str = "",
    screenshot_bytes: Optional[bytes] = None,
    extra_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Persist snapshot artifacts to ``out_dir``. Returns path metadata (relative to DATA_DIR when possible)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    text_path = out_dir / "page.txt"
    html_path = out_dir / "page.html"
    shot_path = out_dir / "screenshot.png"
    meta_path = out_dir / "meta.json"

    text_path.write_text(text or "", encoding="utf-8", errors="replace")
    if html:
        # Cap HTML size to keep disk sane (~2.5MB)
        html_path.write_text((html or "")[:2_500_000], encoding="utf-8", errors="replace")

    if screenshot_bytes:
        shot_path.write_bytes(screenshot_bytes)

    meta = {
        "url": url,
        "final_url": final_url or url,
        "title": title,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "has_screenshot": bool(screenshot_bytes),
        "has_html": bool(html),
        "text_chars": len(text or ""),
        **(extra_meta or {}),
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    def _rel(p: Path) -> str:
        try:
            return str(p.relative_to(DATA_DIR)).replace("\\", "/")
        except ValueError:
            return str(p)

    return {
        "snapshot_dir": _rel(out_dir),
        "screenshot_path": _rel(shot_path) if shot_path.exists() else None,
        "text_path": _rel(text_path),
        "html_path": _rel(html_path) if html_path.exists() else None,
        "meta_path": _rel(meta_path),
        "absolute_dir": str(out_dir),
    }


def resolve_data_path(rel_or_abs: str) -> Path:
    p = Path(rel_or_abs)
    if p.is_absolute():
        return p
    return DATA_DIR / p


def read_snapshot_text(snapshot_dir: str) -> str:
    d = resolve_data_path(snapshot_dir)
    txt = d / "page.txt"
    if txt.exists():
        return txt.read_text(encoding="utf-8", errors="replace")
    return ""


def attach_pending_snapshot_to_candidate(
    *,
    candidate_id: int,
    snapshot_info: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Move a by_url snapshot under cand_{id} and register the DB row."""
    if not snapshot_info or not snapshot_info.get("absolute_dir"):
        return None
    src = Path(snapshot_info["absolute_dir"])
    if not src.exists():
        return snapshot_info

    dest_parent = SNAPSHOTS_ROOT / f"cand_{int(candidate_id)}"
    dest_parent.mkdir(parents=True, exist_ok=True)
    dest = dest_parent / src.name
    if dest.exists():
        dest = dest_parent / f"{src.name}-{url_key(str(candidate_id))}"
    try:
        shutil.move(str(src), str(dest))
    except Exception as exc:
        logger.warning("Could not move snapshot to candidate folder: %s", exc)
        dest = src

    # Rebuild relative paths
    info = dict(snapshot_info)
    try:
        info["snapshot_dir"] = str(dest.relative_to(DATA_DIR)).replace("\\", "/")
        info["absolute_dir"] = str(dest)
        for key, name in (
            ("screenshot_path", "screenshot.png"),
            ("text_path", "page.txt"),
            ("html_path", "page.html"),
            ("meta_path", "meta.json"),
        ):
            fp = dest / name
            if fp.exists():
                info[key] = str(fp.relative_to(DATA_DIR)).replace("\\", "/")
    except Exception:
        pass

    register_snapshot_record(candidate_id=candidate_id, snapshot_info=info)
    return info


def register_snapshot_record(
    *,
    candidate_id: int,
    snapshot_info: Dict[str, Any],
) -> None:
    """Insert CandidateProfileSnapshot row (best-effort)."""
    try:
        from app.candidates.models import CandidateProfileSnapshot
        from app.infrastructure.db import SessionFactory

        with SessionFactory() as db:
            row = CandidateProfileSnapshot(
                candidate_id=candidate_id,
                source_url=(snapshot_info.get("url") or "")[:500] or None,
                snapshot_dir=snapshot_info.get("snapshot_dir") or "",
                screenshot_path=snapshot_info.get("screenshot_path"),
                text_path=snapshot_info.get("text_path"),
                html_path=snapshot_info.get("html_path"),
            )
            db.add(row)
            db.commit()
    except Exception as exc:
        logger.warning("Failed to register snapshot record: %s", exc)


def list_snapshots_for_candidate(candidate_id: int) -> List[Dict[str, Any]]:
    try:
        from sqlalchemy import select

        from app.candidates.models import CandidateProfileSnapshot
        from app.infrastructure.db import SessionFactory

        with SessionFactory() as db:
            rows = list(
                db.scalars(
                    select(CandidateProfileSnapshot)
                    .where(CandidateProfileSnapshot.candidate_id == candidate_id)
                    .order_by(CandidateProfileSnapshot.created_at.desc())
                    .limit(20)
                ).all()
            )
            return [
                {
                    "id": r.id,
                    "snapshot_dir": r.snapshot_dir,
                    "screenshot_path": r.screenshot_path,
                    "text_path": r.text_path,
                    "html_path": r.html_path,
                    "source_url": r.source_url,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]
    except Exception as exc:
        logger.warning("list_snapshots_for_candidate failed: %s", exc)
        return []
