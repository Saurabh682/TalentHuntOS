"""Database infrastructure for TalentHunt OS using SQLAlchemy 2.0."""

from datetime import datetime, timezone
from typing import Generator
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    scoped_session,
    sessionmaker,
    Session,
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

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(120), unique=True, index=True, nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    role: Mapped[str] = mapped_column(String(30), default="user", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    ai_settings: Mapped[list["AISettings"]] = relationship("AISettings", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}')>"


class AISettings(Base):
    """User/System AI engine configuration settings."""
    __tablename__ = "ai_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    default_provider: Mapped[str] = mapped_column(String(50), default="gemini", nullable=False)
    default_model: Mapped[str] = mapped_column(String(100), default="gemini-1.5-flash", nullable=False)
    temperature: Mapped[float] = mapped_column(Float, default=0.7, nullable=False)
    max_tokens: Mapped[int] = mapped_column(Integer, default=2048, nullable=False)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
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


def init_db() -> None:
    """Initialize SQLite database tables and apply automatic schema migrations.

    Safe to call from every page — runs create_all / migrations only once per process.
    """
    global _db_initialized
    if _db_initialized:
        return

    import app.hunts.models  # Register models with Base.metadata
    import app.candidates.models  # Register candidate models with Base.metadata
    import app.communications.models  # Register communications models with Base.metadata
    Base.metadata.create_all(bind=engine)

    # Auto-migration for SQLite missing columns
    try:
        with engine.connect() as conn:
            # 1. hunt_candidates candidate_id + source context
            res = conn.exec_driver_sql("PRAGMA table_info(hunt_candidates)").fetchall()
            cols = [r[1] for r in res]
            if res and "candidate_id" not in cols:
                conn.exec_driver_sql("ALTER TABLE hunt_candidates ADD COLUMN candidate_id INTEGER REFERENCES candidates(id)")
                conn.commit()
            if res:
                hc_expected = {
                    "source_platform": "VARCHAR(50)",
                    "source_query": "TEXT",
                }
                for col_name, col_type in hc_expected.items():
                    if col_name not in cols:
                        conn.exec_driver_sql(f"ALTER TABLE hunt_candidates ADD COLUMN {col_name} {col_type}")
                conn.commit()

            # 2. hunt_search_configs missing columns
            sc_res = conn.exec_driver_sql("PRAGMA table_info(hunt_search_configs)").fetchall()
            sc_cols = [r[1] for r in sc_res]
            if sc_res:
                expected_cols = {
                    "keywords": "TEXT",
                    "required_skills": "TEXT",
                    "preferred_skills": "TEXT",
                    "experience_years_min": "INTEGER",
                    "experience_years_max": "INTEGER",
                    "locations": "VARCHAR(255)",
                    "industry": "VARCHAR(100)",
                    "remote_policy": "VARCHAR(50)",
                    "target_platforms": "TEXT",
                }
                for col_name, col_type in expected_cols.items():
                    if col_name not in sc_cols:
                        conn.exec_driver_sql(f"ALTER TABLE hunt_search_configs ADD COLUMN {col_name} {col_type}")
                conn.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Schema migration error ignored: {e}")

    _db_initialized = True


def get_db() -> Generator[Session, None, None]:
    """Dependency generator for database sessions."""
    db = SessionFactory()
    try:
        yield db
    finally:
        db.close()
