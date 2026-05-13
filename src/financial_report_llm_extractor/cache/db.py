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
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(CREATE_EXTRACTIONS_TABLE_SQL)
        conn.executescript(CREATE_FIELD_VALUES_TABLE_SQL)
        conn.executescript(CREATE_FIELD_VALUES_INDEXES_SQL)
        conn.commit()
    finally:
        conn.close()


def connect(db_path: Path) -> sqlite3.Connection:
    """Open a connection with FK enforcement + 10-second busy timeout."""
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
