"""Single-recruiter authentication with password hashing and signed sessions."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from pathlib import Path
from typing import Any

from sqlalchemy import select, update

from app.config.settings import DATA_DIR

SESSION_COOKIE = "talenthunt_session"
SESSION_TTL_SECONDS = 12 * 60 * 60
PBKDF2_ITERATIONS = 600_000


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _auth_key_path() -> Path:
    path = DATA_DIR / ".secrets" / "auth.key"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_auth_key() -> bytes:
    """Load a stable local signing key, preferring the OS credential vault."""
    try:
        import keyring

        stored = keyring.get_password("TalentHuntOS", "auth_session_key")
        if stored:
            return _b64decode(stored)
        key = secrets.token_bytes(32)
        keyring.set_password("TalentHuntOS", "auth_session_key", _b64encode(key))
        return key
    except Exception:
        key_path = _auth_key_path()
        if key_path.exists():
            return key_path.read_bytes()
        key = secrets.token_bytes(32)
        key_path.write_bytes(key)
        try:
            key_path.chmod(0o600)
        except OSError:
            pass
        return key


def storage_secret() -> str:
    return _b64encode(get_auth_key())


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Password must be at least 12 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${_b64encode(salt)}${_b64encode(digest)}"


def verify_password(password: str, encoded: str | None) -> bool:
    try:
        algorithm, rounds, salt, expected = (encoded or "").split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), _b64decode(salt), int(rounds)
        )
        return hmac.compare_digest(digest, _b64decode(expected))
    except (TypeError, ValueError):
        return False


def create_session_token(username: str) -> str:
    payload = {
        "sub": username,
        "exp": int(time.time()) + SESSION_TTL_SECONDS,
        "nonce": secrets.token_hex(8),
    }
    encoded = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _b64encode(hmac.new(get_auth_key(), encoded.encode("ascii"), hashlib.sha256).digest())
    return f"{encoded}.{signature}"


def decode_session_token(token: str | None) -> dict[str, Any] | None:
    try:
        encoded, signature = (token or "").split(".", 1)
        expected = hmac.new(get_auth_key(), encoded.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64decode(signature)):
            return None
        payload = json.loads(_b64decode(encoded))
        if not isinstance(payload, dict) or int(payload.get("exp", 0)) < int(time.time()):
            return None
        if not payload.get("sub"):
            return None
        return payload
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def has_admin() -> bool:
    from app.infrastructure.db import SessionFactory, init_db
    from app.infrastructure.db import User

    init_db()
    with SessionFactory() as db:
        return db.scalar(
            select(User.id).where(User.role == "admin", User.is_active.is_(True)).limit(1)
        ) is not None


def create_admin(username: str, password: str) -> tuple[bool, str]:
    from app.infrastructure.db import SessionFactory, User, init_db

    init_db()
    clean_username = (username or "").strip()
    if len(clean_username) < 3:
        return False, "Username must be at least 3 characters"
    try:
        password_hash = hash_password(password)
    except ValueError as exc:
        return False, str(exc)

    with SessionFactory() as db:
        if db.scalar(select(User.id).where(User.role == "admin").limit(1)) is not None:
            return False, "Administrator setup is already complete"
        user = User(
            username=clean_username,
            role="admin",
            is_active=True,
            password_hash=password_hash,
        )
        db.add(user)
        db.commit()
    return True, "Administrator created"


def authenticate(username: str, password: str) -> bool:
    from app.infrastructure.db import SessionFactory, User, init_db

    init_db()
    with SessionFactory() as db:
        user = db.scalar(
            select(User).where(
                User.username == (username or "").strip(),
                User.role == "admin",
                User.is_active.is_(True),
            )
        )
        return bool(user and verify_password(password, user.password_hash))


def reset_admin_password(new_password: str) -> tuple[bool, str]:
    """Reset the single local administrator password from trusted local code."""
    from app.infrastructure.db import SessionFactory, User, init_db

    try:
        password_hash = hash_password(new_password)
    except ValueError as exc:
        return False, str(exc)
    init_db()
    with SessionFactory() as db:
        result = db.execute(
            update(User)
            .where(User.role == "admin", User.is_active.is_(True))
            .values(password_hash=password_hash)
        )
        if result.rowcount != 1:
            db.rollback()
            return False, "No active local administrator was found"
        db.commit()
    return True, "Administrator password reset"


def is_authenticated(token: str | None) -> bool:
    payload = decode_session_token(token)
    if not payload:
        return False

    from app.infrastructure.db import SessionFactory, User, init_db

    init_db()
    with SessionFactory() as db:
        return db.scalar(
            select(User.id).where(
                User.username == payload["sub"],
                User.role == "admin",
                User.is_active.is_(True),
            ).limit(1)
        ) is not None


def get_active_admin_id() -> int | None:
    """Return the sole active local administrator ID for trusted in-app adapters."""
    from app.infrastructure.db import SessionFactory, User, init_db

    init_db()
    with SessionFactory() as db:
        return db.scalar(
            select(User.id).where(
                User.role == "admin",
                User.is_active.is_(True),
            ).limit(1)
        )
