"""Small, versioned SQLite migration runner with pre-migration backups."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from sqlalchemy import Engine
from sqlalchemy.engine import Connection
from sqlalchemy.sql.schema import MetaData

logger = logging.getLogger("talenthunt.infrastructure.migrations")


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    apply: Callable[[Connection], None]


def _table_columns(conn: Connection, table: str) -> set[str]:
    rows = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
    return {str(row[1]) for row in rows}


def _legacy_schema_compatibility(conn: Connection) -> None:
    hunt_candidate_columns = _table_columns(conn, "hunt_candidates")
    if hunt_candidate_columns:
        expected = {
            "candidate_id": "INTEGER REFERENCES candidates(id)",
            "source_platform": "VARCHAR(50)",
            "source_query": "TEXT",
        }
        for name, sql_type in expected.items():
            if name not in hunt_candidate_columns:
                conn.exec_driver_sql(
                    f"ALTER TABLE hunt_candidates ADD COLUMN {name} {sql_type}"
                )

    search_config_columns = _table_columns(conn, "hunt_search_configs")
    if search_config_columns:
        expected = {
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
        for name, sql_type in expected.items():
            if name not in search_config_columns:
                conn.exec_driver_sql(
                    f"ALTER TABLE hunt_search_configs ADD COLUMN {name} {sql_type}"
                )

    if _table_columns(conn, "candidate_intake_submissions"):
        conn.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_candidate_intake_submission_request "
            "ON candidate_intake_submissions(request_id)"
        )

    user_columns = _table_columns(conn, "users")
    if user_columns and "password_hash" not in user_columns:
        conn.exec_driver_sql(
            "ALTER TABLE users ADD COLUMN password_hash VARCHAR(255)"
        )
    if user_columns:
        conn.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_single_admin_role "
            "ON users(role) WHERE role = 'admin'"
        )


def _action_execution_ledger(conn: Connection) -> None:
    conn.exec_driver_sql(
        "CREATE TABLE IF NOT EXISTS action_executions ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "action_name VARCHAR(120) NOT NULL, "
        "action_version INTEGER NOT NULL DEFAULT 1, "
        "classification VARCHAR(30) NOT NULL, "
        "risk_level VARCHAR(10) NOT NULL, "
        "actor_type VARCHAR(30) NOT NULL, "
        "session_id VARCHAR(120), "
        "request_id VARCHAR(64) NOT NULL, "
        "idempotency_key VARCHAR(160), "
        "status VARCHAR(30) NOT NULL DEFAULT 'running', "
        "input_json TEXT NOT NULL DEFAULT '{}', "
        "output_json TEXT, "
        "error TEXT, "
        "duration_ms FLOAT, "
        "created_at DATETIME NOT NULL, "
        "completed_at DATETIME"
        ")"
    )
    conn.exec_driver_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_action_executions_idempotency_key "
        "ON action_executions(idempotency_key)"
    )
    for column in ("action_name", "actor_type", "session_id", "request_id", "status", "created_at"):
        conn.exec_driver_sql(
            f"CREATE INDEX IF NOT EXISTS ix_action_executions_{column} "
            f"ON action_executions({column})"
        )


def _linkedin_profile_capture(conn: Connection) -> None:
    additions = {
        "candidates": {
            "pronouns": "VARCHAR(50)",
            "connection_degree": "VARCHAR(30)",
            "connections_count": "INTEGER",
            "profile_image_url": "VARCHAR(500)",
        },
        "candidate_profiles": {"highlights_json": "TEXT"},
        "candidate_experiences": {
            "employment_type": "VARCHAR(50)",
            "skills_json": "TEXT",
        },
        "candidate_educations": {
            "grade": "VARCHAR(100)",
            "activities": "TEXT",
            "description": "TEXT",
        },
    }
    for table, columns in additions.items():
        existing = _table_columns(conn, table)
        if not existing:
            continue
        for name, sql_type in columns.items():
            if name not in existing:
                conn.exec_driver_sql(
                    f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"
                )


def _pending_action_approvals(conn: Connection) -> None:
    conn.exec_driver_sql(
        "CREATE TABLE IF NOT EXISTS pending_action_approvals ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "action_name VARCHAR(120) NOT NULL, "
        "action_version INTEGER NOT NULL DEFAULT 1, "
        "fingerprint VARCHAR(64) NOT NULL, "
        "user_id INTEGER NOT NULL, "
        "actor_type VARCHAR(30) NOT NULL, "
        "session_id VARCHAR(120) NOT NULL, "
        "request_id VARCHAR(64) NOT NULL, "
        "status VARCHAR(30) NOT NULL DEFAULT 'pending', "
        "input_json TEXT NOT NULL, "
        "preview_json TEXT NOT NULL, "
        "token_hash VARCHAR(64), "
        "created_at DATETIME NOT NULL, "
        "expires_at DATETIME NOT NULL, "
        "approved_at DATETIME, "
        "consumed_at DATETIME, "
        "cancelled_at DATETIME"
        ")"
    )
    conn.exec_driver_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_pending_action_approvals_token_hash "
        "ON pending_action_approvals(token_hash)"
    )
    for column in ("action_name", "fingerprint", "user_id", "session_id", "request_id", "status", "created_at", "expires_at"):
        conn.exec_driver_sql(
            f"CREATE INDEX IF NOT EXISTS ix_pending_action_approvals_{column} "
            f"ON pending_action_approvals({column})"
        )


def _action_resource_locks(conn: Connection) -> None:
    conn.exec_driver_sql(
        "CREATE TABLE IF NOT EXISTS action_resource_locks ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "lease_id VARCHAR(64) NOT NULL, "
        "resource_key VARCHAR(180) NOT NULL, "
        "action_name VARCHAR(120) NOT NULL, "
        "request_id VARCHAR(64) NOT NULL, "
        "user_id INTEGER, "
        "session_id VARCHAR(120), "
        "status VARCHAR(30) NOT NULL DEFAULT 'active', "
        "acquired_at DATETIME NOT NULL, "
        "expires_at DATETIME NOT NULL, "
        "released_at DATETIME"
        ")"
    )
    conn.exec_driver_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_action_resource_locks_active_resource "
        "ON action_resource_locks(resource_key) WHERE status = 'active'"
    )
    for column in (
        "lease_id", "resource_key", "action_name", "request_id", "user_id",
        "session_id", "status", "expires_at",
    ):
        conn.exec_driver_sql(
            f"CREATE INDEX IF NOT EXISTS ix_action_resource_locks_{column} "
            f"ON action_resource_locks({column})"
        )


def _action_tool_calls(conn: Connection) -> None:
    conn.exec_driver_sql(
        "CREATE TABLE IF NOT EXISTS action_tool_calls ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "tool_call_id VARCHAR(64) NOT NULL, "
        "tool_name VARCHAR(120) NOT NULL, "
        "action_name VARCHAR(120), "
        "action_execution_id INTEGER, "
        "actor_type VARCHAR(30) NOT NULL DEFAULT 'agent', "
        "session_id VARCHAR(120), "
        "status VARCHAR(30) NOT NULL DEFAULT 'running', "
        "input_json TEXT NOT NULL DEFAULT '{}', "
        "output_json TEXT, "
        "error TEXT, "
        "duration_ms FLOAT, "
        "started_at DATETIME NOT NULL, "
        "completed_at DATETIME"
        ")"
    )
    conn.exec_driver_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_action_tool_calls_tool_call_id "
        "ON action_tool_calls(tool_call_id)"
    )
    for column in (
        "tool_name", "action_name", "action_execution_id", "actor_type",
        "session_id", "status", "started_at",
    ):
        conn.exec_driver_sql(
            f"CREATE INDEX IF NOT EXISTS ix_action_tool_calls_{column} "
            f"ON action_tool_calls({column})"
        )


def _background_jobs(conn: Connection) -> None:
    conn.exec_driver_sql(
        "CREATE TABLE IF NOT EXISTS background_jobs ("
        "id VARCHAR(32) PRIMARY KEY, "
        "kind VARCHAR(60) NOT NULL, "
        "status VARCHAR(30) NOT NULL DEFAULT 'running', "
        "hunt_id INTEGER, "
        "hunt_title VARCHAR(255), "
        "label VARCHAR(255) NOT NULL, "
        "message TEXT NOT NULL DEFAULT 'Starting...', "
        "scanned INTEGER NOT NULL DEFAULT 0, "
        "added INTEGER NOT NULL DEFAULT 0, "
        "skipped INTEGER NOT NULL DEFAULT 0, "
        "payload_json TEXT NOT NULL DEFAULT '{}', "
        "progress_json TEXT NOT NULL DEFAULT '{}', "
        "result_json TEXT, "
        "error TEXT, "
        "attempt INTEGER NOT NULL DEFAULT 1, "
        "parent_job_id VARCHAR(32), "
        "retryable BOOLEAN NOT NULL DEFAULT 1, "
        "notified BOOLEAN NOT NULL DEFAULT 0, "
        "created_at DATETIME NOT NULL, "
        "started_at DATETIME NOT NULL, "
        "heartbeat_at DATETIME NOT NULL, "
        "cancel_requested_at DATETIME, "
        "finished_at DATETIME, "
        "notified_at DATETIME"
        ")"
    )
    conn.exec_driver_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_background_jobs_active_sourcing "
        "ON background_jobs(kind) WHERE kind = 'sourcing' AND status = 'running'"
    )
    for column in (
        "kind", "status", "hunt_id", "parent_job_id", "created_at",
        "started_at", "heartbeat_at", "finished_at",
    ):
        conn.exec_driver_sql(
            f"CREATE INDEX IF NOT EXISTS ix_background_jobs_{column} "
            f"ON background_jobs({column})"
        )


MIGRATIONS = (
    Migration(1, "legacy_schema_compatibility", _legacy_schema_compatibility),
    Migration(2, "action_execution_ledger", _action_execution_ledger),
    Migration(3, "linkedin_profile_capture", _linkedin_profile_capture),
    Migration(4, "pending_action_approvals", _pending_action_approvals),
    Migration(5, "action_resource_locks", _action_resource_locks),
    Migration(6, "action_tool_calls", _action_tool_calls),
    Migration(7, "background_jobs", _background_jobs),
)


def _existing_application_database(engine: Engine) -> bool:
    with engine.connect() as conn:
        count = conn.exec_driver_sql(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
            "AND name != 'schema_migrations'"
        ).scalar_one()
    return bool(count)


def _applied_versions(engine: Engine) -> set[int]:
    with engine.connect() as conn:
        exists = conn.exec_driver_sql(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
        ).first()
        if not exists:
            return set()
        return {
            int(row[0])
            for row in conn.exec_driver_sql(
                "SELECT version FROM schema_migrations"
            ).fetchall()
        }


def backup_database(db_path: Path, *, target_version: int) -> Path:
    """Create a consistent SQLite backup, including data currently held in WAL."""
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = backup_dir / f"{db_path.stem}-before-v{target_version}-{stamp}.db"
    with sqlite3.connect(db_path) as source, sqlite3.connect(target) as destination:
        source.backup(destination)
    return target


def run_schema_migrations(engine: Engine, db_path: Path, metadata: MetaData) -> list[int]:
    """Create current tables, apply pending migrations, and return applied versions."""
    applied = _applied_versions(engine)
    pending = [migration for migration in MIGRATIONS if migration.version not in applied]
    database_exists = _existing_application_database(engine)

    if pending and database_exists and db_path.exists() and db_path.stat().st_size:
        backup = backup_database(db_path, target_version=pending[-1].version)
        logger.info("Created pre-migration database backup at %s", backup)

    metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version INTEGER PRIMARY KEY, "
            "name VARCHAR(150) NOT NULL, "
            "applied_at VARCHAR(40) NOT NULL"
            ")"
        )

    completed: list[int] = []
    for migration in pending:
        with engine.begin() as conn:
            migration.apply(conn)
            conn.exec_driver_sql(
                "INSERT INTO schema_migrations(version, name, applied_at) VALUES (?, ?, ?)",
                (
                    migration.version,
                    migration.name,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        completed.append(migration.version)
        logger.info("Applied schema migration %s: %s", migration.version, migration.name)
    return completed
