"""SQLite connection + schema initialization for the extraction cache."""

import sqlite3
from pathlib import Path

from financial_report_llm_extractor.cache.db_schema import (
    CREATE_EXTRACTIONS_TABLE_SQL,
    CREATE_FIELD_VALUES_INDEXES_SQL,
    CREATE_FIELD_VALUES_TABLE_SQL,
)


def init_db(db_path: Path) -> None:
    """Create the DB file and apply schema if not present.

    Idempotent: safe to call against an already-initialized DB.
    Creates parent directories as needed.

    Schema migration: if `field_values` table exists but lacks `market` column
    (v1→v2) or lacks `normalized_value` column (v2→v3), drops the table and
    recreates with the current schema. Operator must re-run
    `financial-report-llm-extractor index ...` after migration to repopulate.
    tmp/runs/* artifacts are unaffected.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists() and _is_legacy_schema(db_path):
        _drop_legacy_tables(db_path)
    conn = connect(db_path)
    try:
        conn.executescript(CREATE_EXTRACTIONS_TABLE_SQL)
        conn.executescript(CREATE_FIELD_VALUES_TABLE_SQL)
        conn.executescript(CREATE_FIELD_VALUES_INDEXES_SQL)
        conn.commit()
    finally:
        conn.close()


def _is_legacy_schema(db_path: Path) -> bool:
    """Detect legacy field_values schema (lacks market column or normalized_value).

    Returns True for:
    - R1 v1 schema: missing ``market`` column
    - R5 v2 schema: has ``market`` but missing ``normalized_value`` (schema v3
      added normalized_value + canonical_unit columns)
    """
    conn = sqlite3.connect(db_path)
    try:
        rows = list(conn.execute("PRAGMA table_info(field_values)"))
    except sqlite3.OperationalError:
        return False  # table doesn't exist, fresh DB
    finally:
        conn.close()
    if not rows:
        return False  # table doesn't exist
    column_names = {r[1] for r in rows}  # PRAGMA returns (cid, name, type, ...)
    return "market" not in column_names or "normalized_value" not in column_names


def _drop_legacy_tables(db_path: Path) -> None:
    """Drop legacy v1 field_values + indexes AND extractions.

    Both tables are recreated by init_db() with v2 schema. All legacy data
    is lost; tmp/runs/* artifacts remain the source of truth and operator
    must re-index via `financial-report-llm-extractor index ...`.
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            "DROP INDEX IF EXISTS idx_field_values_field;\n"
            "DROP INDEX IF EXISTS idx_field_values_bucket;\n"
            "DROP INDEX IF EXISTS idx_field_values_priority;\n"
            "DROP TABLE IF EXISTS field_values;"
        )
        # extractions table is also wiped because field_values references it
        # logically. Cleaner to start fresh.
        conn.executescript("DROP TABLE IF EXISTS extractions;")
        conn.commit()
    finally:
        conn.close()


def connect(db_path: Path) -> sqlite3.Connection:
    """Open a connection with a 10-second busy timeout for soft concurrency."""
    return sqlite3.connect(db_path, timeout=10.0)
