"""init_db() creates tables + indexes; connect() opens with timeout."""

import sqlite3
from pathlib import Path

from financial_report_llm_extractor.cache.db import connect, init_db


def test_init_db_creates_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    init_db(db_path)
    assert db_path.exists()

    conn = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "extractions" in tables
        assert "field_values" in tables
    finally:
        conn.close()


def test_init_db_creates_indexes(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        indexes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
        }
        for idx in (
            "idx_field_values_field",
            "idx_field_values_bucket",
            "idx_field_values_priority",
            "idx_field_values_market",  # R5
        ):
            assert idx in indexes
    finally:
        conn.close()


def test_init_db_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    init_db(db_path)
    init_db(db_path)  # second call must not raise


def test_init_db_creates_parent_dir(tmp_path: Path) -> None:
    db_path = tmp_path / "subdir" / "test.db"
    init_db(db_path)
    assert db_path.exists()


def test_connect_returns_usable_connection(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    init_db(db_path)
    conn = connect(db_path)
    try:
        # Must be able to query without error.
        rows = list(conn.execute("SELECT COUNT(*) FROM extractions"))
        assert rows == [(0,)]
    finally:
        conn.close()


def test_field_values_insert_works_without_parent_extractions(
    tmp_path: Path,
) -> None:
    """Regression: verify the field_values FK was correctly dropped.

    A latent schema bug (Task 1+2 review) made INSERT into field_values
    fail with OperationalError because the FOREIGN KEY referenced a
    partial primary key of extractions. After the fix, field_values
    rows can be inserted independently — the indexer enforces the
    latest-catalog-version relationship at application level.
    """
    db_path = tmp_path / "test.db"
    init_db(db_path)
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO field_values "
            "(company, period_end, market, field_id, bucket) "
            "VALUES (?, ?, ?, ?, ?)",
            ("600519", "2024-12-31", "CN", "revenue", "clean_present"),
        )
        conn.commit()
        rows = list(conn.execute("SELECT COUNT(*) FROM field_values"))
        assert rows == [(1,)]
    finally:
        conn.close()


def test_init_db_migrates_legacy_v1_field_values_schema(tmp_path: Path) -> None:
    """R5 migration: init_db detects v1 field_values schema (no market column)
    and drops + recreates with v2 schema."""
    db_path = tmp_path / "legacy.db"

    # Manually create v1 schema (legacy field_values without market column)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript("""
            CREATE TABLE extractions (
              company TEXT NOT NULL,
              period_end TEXT NOT NULL,
              market TEXT NOT NULL,
              report_type TEXT NOT NULL,
              catalog_version TEXT NOT NULL,
              schema_version TEXT NOT NULL,
              generated_at TEXT NOT NULL,
              artifact_path TEXT NOT NULL,
              llm_provider TEXT,
              llm_model TEXT,
              PRIMARY KEY (company, period_end, market, catalog_version)
            );
            CREATE TABLE field_values (
              company TEXT NOT NULL,
              period_end TEXT NOT NULL,
              field_id TEXT NOT NULL,
              priority TEXT,
              bucket TEXT NOT NULL,
              value TEXT,
              currency TEXT,
              unit TEXT,
              selected_source TEXT,
              reason TEXT,
              evidence_page INTEGER,
              llm_confidence REAL,
              llm_reasoning_short TEXT,
              PRIMARY KEY (company, period_end, field_id)
            );
        """)
        # Seed some legacy rows
        conn.execute(
            "INSERT INTO field_values (company, period_end, field_id, bucket) "
            "VALUES ('600519', '2024-12-31', 'revenue', 'clean_present')"
        )
        conn.commit()
    finally:
        conn.close()

    # Trigger migration via init_db
    init_db(db_path)

    # Verify v2 schema present
    conn = sqlite3.connect(db_path)
    try:
        rows = list(conn.execute("PRAGMA table_info(field_values)"))
        column_names = {r[1] for r in rows}
        assert "market" in column_names, "migration failed to add market column"
        # Legacy data is dropped (fresh schema)
        count = conn.execute("SELECT COUNT(*) FROM field_values").fetchone()[0]
        assert count == 0, "legacy rows should be dropped on migration"
    finally:
        conn.close()


def test_init_db_idempotent_on_v2_schema(tmp_path: Path) -> None:
    """Calling init_db twice on v2 schema is a no-op (no spurious migration)."""
    db_path = tmp_path / "v2.db"
    init_db(db_path)  # creates v2 fresh

    # Seed a v2 row
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO field_values "
            "(company, period_end, market, field_id, bucket) "
            "VALUES ('600519', '2024-12-31', 'CN', 'revenue', 'clean_present')"
        )
        conn.commit()
    finally:
        conn.close()

    # Second init_db should NOT drop the row
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    try:
        count = conn.execute("SELECT COUNT(*) FROM field_values").fetchone()[0]
    finally:
        conn.close()
    assert count == 1, "v2 → v2 must not drop existing rows"
