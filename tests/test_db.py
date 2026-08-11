import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.infrastructure.db import (
    User,
    AISettings,
    LocalModelRegistry,
    FeatureFlag,
    init_db,
    get_db,
    Base
)

@pytest.fixture(scope="module")
def db_session():
    # Use an in-memory SQLite database for testing models
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    test_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(test_engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(test_engine)

def test_user_model(db_session: Session):
    user = User(username="testuser", email="test@example.com", role="admin")
    db_session.add(user)
    db_session.commit()
    
    saved_user = db_session.query(User).filter_by(username="testuser").first()
    assert saved_user is not None
    assert saved_user.id is not None
    assert saved_user.email == "test@example.com"
    assert saved_user.role == "admin"
    assert saved_user.is_active is True
    assert saved_user.created_at is not None
    assert saved_user.updated_at is not None
    assert "<User(id=" in repr(saved_user)
    assert "username='testuser'" in repr(saved_user)

def test_ai_settings_model(db_session: Session):
    user = User(username="aiuser")
    db_session.add(user)
    db_session.commit()
    
    settings = AISettings(user_id=user.id, default_provider="openai", default_model="gpt-4")
    db_session.add(settings)
    db_session.commit()
    
    saved_settings = db_session.query(AISettings).filter_by(user_id=user.id).first()
    assert saved_settings is not None
    assert saved_settings.default_provider == "openai"
    assert saved_settings.default_model == "gpt-4"
    assert saved_settings.temperature == 0.7
    assert saved_settings.max_tokens == 2048
    assert "<AISettings(id=" in repr(saved_settings)

def test_local_model_registry_model(db_session: Session):
    registry = LocalModelRegistry(model_name="llama3", file_path="/models/llama3.gguf")
    db_session.add(registry)
    db_session.commit()
    
    saved_registry = db_session.query(LocalModelRegistry).filter_by(model_name="llama3").first()
    assert saved_registry is not None
    assert saved_registry.file_path == "/models/llama3.gguf"
    assert saved_registry.context_length == 4096
    assert saved_registry.is_downloaded is False
    assert saved_registry.is_active is False
    assert "<LocalModelRegistry(id=" in repr(saved_registry)

def test_feature_flag_model(db_session: Session):
    flag = FeatureFlag(flag_key="new_ui", is_enabled=True, description="Test flag")
    db_session.add(flag)
    db_session.commit()
    
    saved_flag = db_session.query(FeatureFlag).filter_by(flag_key="new_ui").first()
    assert saved_flag is not None
    assert saved_flag.is_enabled is True
    assert saved_flag.description == "Test flag"
    assert "<FeatureFlag(key='new_ui'" in repr(saved_flag)

@patch("app.infrastructure.db.Base.metadata.create_all")
def test_init_db(mock_create_all):
    import app.infrastructure.db as db_module

    with patch.dict('sys.modules', {
        'app.hunts.models': MagicMock(),
        'app.candidates.models': MagicMock(),
        'app.communications.models': MagicMock()
    }), patch.object(db_module, "_db_initialized", False):
        init_db()
        mock_create_all.assert_called_once()

def test_get_db():
    gen = get_db()
    session = next(gen)
    assert isinstance(session, Session)
    try:
        next(gen)
    except StopIteration:
        pass
