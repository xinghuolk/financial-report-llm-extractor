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
