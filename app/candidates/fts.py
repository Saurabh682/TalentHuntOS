"""Best-effort SQLite FTS5 filters over canonical candidate records."""

from __future__ import annotations

import logging
import re
from typing import Optional

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import TextClause

logger = logging.getLogger("talenthunt.candidates.fts")

_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
_FTS_STATEMENTS = {
    "candidate": (
        "candidate_search_fts",
        "candidates.id IN ("
        "SELECT CAST(candidate_id AS INTEGER) FROM candidate_search_fts "
        "WHERE candidate_search_fts MATCH :candidate_fts_query)",
        "candidate_fts_query",
    ),
    "discovery": (
        "discovery_search_fts",
        "discovered_profiles.id IN ("
        "SELECT CAST(discovered_profile_id AS INTEGER) FROM discovery_search_fts "
        "WHERE discovery_search_fts MATCH :discovery_fts_query)",
        "discovery_fts_query",
    ),
}


def build_match_query(value: str) -> str:
    """Build a literal prefix query without accepting raw FTS operators."""
    tokens = _TOKEN_RE.findall((value or "").casefold())
    return " AND ".join(f'"{token.replace(chr(34), chr(34) * 2)}"*' for token in tokens[:12])


def _fts_table_available(db: Session, table: str) -> bool:
    try:
        return (
            db.execute(
                text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = :name"),
                {"name": table},
            ).first()
            is not None
        )
    except SQLAlchemyError:
        return False


def _fts_clause(
    db: Session,
    *,
    index: str,
    query: str,
) -> Optional[TextClause]:
    table, statement, parameter = _FTS_STATEMENTS[index]
    match_query = build_match_query(query)
    if not match_query or not _fts_table_available(db, table):
        return None
    clause = text(statement)
    return clause.bindparams(**{parameter: match_query})


def candidate_search_clause(db: Session, query: str) -> Optional[TextClause]:
    return _fts_clause(
        db,
        index="candidate",
        query=query,
    )


def discovery_search_clause(db: Session, query: str) -> Optional[TextClause]:
    return _fts_clause(
        db,
        index="discovery",
        query=query,
    )
