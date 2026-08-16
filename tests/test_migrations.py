import sqlite3

from sqlalchemy import create_engine

import app.candidates.models  # noqa: F401
from app.infrastructure.db import Base
from app.infrastructure.migrations import run_schema_migrations


def test_migration_creates_backup_records_version_and_is_idempotent(tmp_path):
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE users ("
            "id INTEGER PRIMARY KEY, username VARCHAR(50), role VARCHAR(30) NOT NULL"
            ")"
        )
        conn.execute("INSERT INTO users(id, username, role) VALUES (1, 'admin', 'admin')")

    engine = create_engine(f"sqlite:///{db_path}")
    assert run_schema_migrations(engine, db_path, Base.metadata) == [
        1,
        2,
        3,
        4,
        5,
        6,
        7,
        8,
        9,
        10,
    ]

    backups = list((tmp_path / "backups").glob("legacy-before-v10-*.db"))
    assert len(backups) == 1
    with engine.connect() as conn:
        columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(users)").fetchall()}
        versions = conn.exec_driver_sql("SELECT version, name FROM schema_migrations").fetchall()
        candidate_columns = {
            row[1] for row in conn.exec_driver_sql("PRAGMA table_info(candidates)").fetchall()
        }
        experience_columns = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(candidate_experiences)").fetchall()
        }
        background_job_columns = {
            row[1] for row in conn.exec_driver_sql("PRAGMA table_info(background_jobs)").fetchall()
        }
        search_tables = {
            row[0]
            for row in conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name IN ('candidate_search_fts', 'discovery_search_fts')"
            ).fetchall()
        }
        communication_columns = {
            row[1] for row in conn.exec_driver_sql("PRAGMA table_info(communications)").fetchall()
        }
        communication_indexes = {
            row[1] for row in conn.exec_driver_sql("PRAGMA index_list(communications)").fetchall()
        }
        report_columns = {
            row[1] for row in conn.exec_driver_sql("PRAGMA table_info(report_artifacts)").fetchall()
        }
    assert "password_hash" in columns
    assert {"pronouns", "connections_count", "profile_image_url"} <= candidate_columns
    assert {"employment_type", "skills_json"} <= experience_columns
    assert {"heartbeat_at", "payload_json", "retryable", "finished_at"} <= background_job_columns
    assert versions == [
        (1, "legacy_schema_compatibility"),
        (2, "action_execution_ledger"),
        (3, "linkedin_profile_capture"),
        (4, "pending_action_approvals"),
        (5, "action_resource_locks"),
        (6, "action_tool_calls"),
        (7, "background_jobs"),
        (8, "candidate_full_text_search"),
        (9, "communication_delivery_receipts"),
        (10, "report_artifacts"),
    ]
    assert search_tables == {"candidate_search_fts", "discovery_search_fts"}
    assert {
        "provider_name",
        "provider_message_id",
        "failure_reason",
        "retry_eligible",
        "delivery_key",
    } <= communication_columns
    assert "ix_communications_delivery_key" in communication_indexes
    assert {
        "id",
        "format",
        "relative_path",
        "sha256",
        "provenance_json",
        "created_at",
    } <= report_columns

    assert run_schema_migrations(engine, db_path, Base.metadata) == []
    assert len(list((tmp_path / "backups").glob("legacy-before-v10-*.db"))) == 1
