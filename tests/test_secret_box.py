from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.communications.models import BrowserSession
from app.communications.service import get_decrypted_cookies_for_platform
from app.infrastructure import secret_box
from app.infrastructure.db import Base


def test_file_key_survives_fernet_reinitialization(monkeypatch, tmp_path):
    import app.config.settings as settings_module

    monkeypatch.setattr(settings_module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(secret_box, "_read_keyring_key", lambda: None)
    secret_box._fernet = None
    try:
        sealed = secret_box.seal("persistent cookie value")
        assert (tmp_path / ".secrets" / "session.key").exists()
        secret_box._fernet = None
        assert secret_box.open_secret(sealed) == "persistent cookie value"
    finally:
        secret_box._fernet = None


def test_undecryptable_browser_session_is_deactivated(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'bad-session.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    with factory() as db:
        row = BrowserSession(
            platform="linkedin",
            session_name="Broken login",
            target_url="https://www.linkedin.com/feed/",
            cookies_json="enc:v1:broken",
            is_active=True,
        )
        db.add(row)
        db.commit()
        session_id = row.id

    monkeypatch.setattr(
        "app.infrastructure.secret_box.open_secret",
        lambda _value: (_ for _ in ()).throw(ValueError("wrong key")),
    )
    with factory() as db:
        assert get_decrypted_cookies_for_platform(db, "linkedin") is None
        restored = db.get(BrowserSession, session_id)
        assert restored.is_active is False
        assert "Reconnect required" in restored.headers_json
