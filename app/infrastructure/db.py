"""Database infrastructure for TalentHunt OS using SQLAlchemy 2.0."""

import threading
from datetime import datetime, timezone
from typing import Generator

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    create_engine,
    event,
    text,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    scoped_session,
    sessionmaker,
)

from app.config.settings import settings


# 1. Base Class definition for SQLAlchemy 2.0
class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


# 2. Model Definitions
class User(Base):
    """User account model."""

    __tablename__ = "users"
    __table_args__ = (
        Index(
            "uq_single_admin_role",
            "role",
            unique=True,
            sqlite_where=text("role = 'admin'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(120), unique=True, index=True, nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    role: Mapped[str] = mapped_column(String(30), default="user", nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    ai_settings: Mapped[list["AISettings"]] = relationship(
        "AISettings", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}')>"


class AISettings(Base):
    """User/System AI engine configuration settings."""

    __tablename__ = "ai_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    default_provider: Mapped[str] = mapped_column(String(50), default="gemini", nullable=False)
    default_model: Mapped[str] = mapped_column(
        String(100), default="gemini-1.5-flash", nullable=False
    )
    temperature: Mapped[float] = mapped_column(Float, default=0.7, nullable=False)
    max_tokens: Mapped[int] = mapped_column(Integer, default=2048, nullable=False)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    user: Mapped[User | None] = relationship("User", back_populates="ai_settings")

    def __repr__(self) -> str:
        return f"<AISettings(id={self.id}, provider='{self.default_provider}', model='{self.default_model}')>"


class LocalModelRegistry(Base):
    """Registry for local GGUF models managed by llama-server."""

    __tablename__ = "local_model_registry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    file_path: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    context_length: Mapped[int] = mapped_column(Integer, default=4096, nullable=False)
    quant_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    is_downloaded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<LocalModelRegistry(id={self.id}, name='{self.model_name}', quant='{self.quant_type}')>"


class FeatureFlag(Base):
    """Runtime feature toggle flags."""

    __tablename__ = "feature_flags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    flag_key: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<FeatureFlag(key='{self.flag_key}', enabled={self.is_enabled})>"


# 3. Database Engine & Session Factory Setup
DATA_DIR = settings.db_path.parent
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_URL = f"sqlite:///{settings.db_path.as_posix()}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 15.0},
    echo=settings.sql_echo,
)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
ScopedSession = scoped_session(SessionFactory)

_db_initialized = False
_db_init_lock = threading.Lock()


def init_db() -> None:
    """Initialize SQLite database tables and apply automatic schema migrations.

    Safe to call from every page — runs create_all / migrations only once per process.
    """
    global _db_initialized
    if _db_initialized:
        return

    with _db_init_lock:
        if _db_initialized:
            return

        import app.actions.models  # Register durable action history with Base.metadata
        import app.analytics.models  # noqa: F401  # Register report artifacts
        from app.infrastructure.migrations import run_schema_migrations

        run_schema_migrations(engine, settings.db_path, Base.metadata)

        _db_initialized = True


def get_db() -> Generator[Session, None, None]:
    """Dependency generator for database sessions."""
    db = SessionFactory()
    try:
        yield db
    finally:
        db.close()
