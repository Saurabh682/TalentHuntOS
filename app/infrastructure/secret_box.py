"""Local secret sealing for TalentHunt OS (Fernet + OS keyring).

Used for browser session cookies — never store site passwords.
Ciphertext is prefixed ``enc:v1:`` so legacy plaintext can still be read once.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("talenthunt.secret_box")

_PREFIX = "enc:v1:"
_SERVICE = "TalentHuntOS"
_KEY_NAME = "browser_session_fernet_key"

_fernet = None


def _key_path() -> Path:
    from app.config.settings import DATA_DIR

    return DATA_DIR / ".secrets" / "session.key"


def _read_keyring_key() -> Optional[bytes]:
    try:
        import keyring

        existing = keyring.get_password(_SERVICE, _KEY_NAME)
        return existing.encode("utf-8") if existing else None
    except Exception as exc:
        logger.debug("keyring unavailable: %s", exc)
        return None


def _load_or_create_key() -> bytes:
    """Return one stable data-directory key across every launch context."""
    from cryptography.fernet import Fernet

    key_path = _key_path()
    if key_path.exists():
        return key_path.read_bytes().strip()

    # Migrate an older keyring-first installation when possible. Once written,
    # the file remains canonical for both desktop and background launches.
    key = _read_keyring_key() or Fernet.generate_key()
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_bytes(key)
    try:
        key_path.chmod(0o600)
    except Exception:
        pass
    return key


def _get_fernet():
    global _fernet
    if _fernet is None:
        from cryptography.fernet import Fernet

        _fernet = Fernet(_load_or_create_key())
    return _fernet


def is_sealed(blob: Optional[str]) -> bool:
    return bool(blob) and str(blob).startswith(_PREFIX)


def seal(plaintext: str) -> str:
    """Encrypt plaintext → ``enc:v1:<token>``."""
    if plaintext is None:
        return ""
    raw = str(plaintext)
    if is_sealed(raw):
        return raw
    token = _get_fernet().encrypt(raw.encode("utf-8")).decode("utf-8")
    return f"{_PREFIX}{token}"


def open_secret(blob: Optional[str]) -> str:
    """Decrypt sealed blob, or return legacy plaintext unchanged."""
    if not blob:
        return ""
    raw = str(blob)
    if not is_sealed(raw):
        return raw
    token = raw[len(_PREFIX) :]
    try:
        return _get_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except Exception as exc:
        legacy_key = _read_keyring_key()
        if legacy_key:
            try:
                from cryptography.fernet import Fernet

                return Fernet(legacy_key).decrypt(token.encode("utf-8")).decode("utf-8")
            except Exception:
                pass
        logger.error("Failed to decrypt stored secret")
        raise ValueError("Could not decrypt stored session (wrong key or corrupt data)") from exc
