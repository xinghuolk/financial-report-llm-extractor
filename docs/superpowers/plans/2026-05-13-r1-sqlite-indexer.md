# R1 SQLite Indexer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a SQLite indexer that scans `tmp/runs/*/evaluation.json` and writes canonical extraction results to `data/extracted.db`, plus `query` CLI command for cross-cohort queries. Zero behavior change to the existing pipeline; this is purely additive.

**Architecture:** New `cache/` sub-package parallel to `structured_sources/`. Read-only with respect to the pipeline: only consumes existing `evaluation.json` artifacts. Uses stdlib `sqlite3`, no new dependencies. Catalog version is read from taxonomy at runtime and forms part of the primary key so future catalog changes auto-version their rows.

**Tech Stack:** Python 3.11 stdlib (`sqlite3`, `json`, `pathlib`, `hashlib`), pytest, project's existing CLI argparse pattern.

---

## File Structure

| File | Role |
|---|---|
| `src/financial_report_llm_extractor/cache/__init__.py` | Package marker |
| `src/financial_report_llm_extractor/cache/db_schema.py` | DDL constants for `extractions` + `field_values` tables |
| `src/financial_report_llm_extractor/cache/db.py` | `init_db()`, connection helper |
| `src/financial_report_llm_extractor/cache/indexer.py` | `index_run(run_dir, db_path)` reads `evaluation.json` + UPSERTs rows |
| `src/financial_report_llm_extractor/cache/db_query.py` | Read-side: `query(...)`, `bulk_query(...)` |
| `src/financial_report_llm_extractor/cli.py` | Add `index` + `query` subcommands |
| `tests/cache/__init__.py` | Package marker for tests |
| `tests/cache/test_db_schema.py` | DDL constants present + parseable |
| `tests/cache/test_db.py` | `init_db()` creates tables |
| `tests/cache/test_indexer.py` | Round-trip: minimal evaluation.json → DB → query |
| `tests/cache/test_db_query.py` | Query single + bulk |
| `tests/cache/fixtures/sample_run/evaluation.json` | 2-field minimal fixture |
| `tests/test_cli.py` (extend) | CLI integration for `index` + `query` |

---

## Task 1: Create cache module skeleton + DDL constants

**Files:**
- Create: `src/financial_report_llm_extractor/cache/__init__.py`
- Create: `src/financial_report_llm_extractor/cache/db_schema.py`
- Create: `tests/cache/__init__.py`
- Test: `tests/cache/test_db_schema.py`

- [ ] **Step 1.1: Write the failing test**

Write `tests/cache/test_db_schema.py`:

```python
"""DDL constants for the extraction cache DB."""

from financial_report_llm_extractor.cache import db_schema


def test_extractions_ddl_contains_primary_key() -> None:
    sql = db_schema.CREATE_EXTRACTIONS_TABLE_SQL
    assert "CREATE TABLE" in sql
    assert "extractions" in sql
    assert "PRIMARY KEY" in sql
    assert "company" in sql
    assert "period_end" in sql
    assert "market" in sql
    assert "catalog_version" in sql


def test_field_values_ddl_contains_foreign_key() -> None:
    sql = db_schema.CREATE_FIELD_VALUES_TABLE_SQL
    assert "CREATE TABLE" in sql
    assert "field_values" in sql
    assert "FOREIGN KEY" in sql
    assert "REFERENCES extractions" in sql
    assert "bucket" in sql
    assert "field_id" in sql


def test_indexes_present() -> None:
    assert "CREATE INDEX" in db_schema.CREATE_FIELD_VALUES_INDEXES_SQL
    assert "idx_field_values_field" in db_schema.CREATE_FIELD_VALUES_INDEXES_SQL
    assert "idx_field_values_bucket" in db_schema.CREATE_FIELD_VALUES_INDEXES_SQL
```

- [ ] **Step 1.2: Run test to verify it fails**

```bash
uv run pytest tests/cache/test_db_schema.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'financial_report_llm_extractor.cache'`.

- [ ] **Step 1.3: Create empty `__init__.py` files**

Create `src/financial_report_llm_extractor/cache/__init__.py` (empty file).
Create `tests/cache/__init__.py` (empty file).

- [ ] **Step 1.4: Implement `db_schema.py`**

Write `src/financial_report_llm_extractor/cache/db_schema.py`:

```python
"""SQLite DDL constants for the extraction result cache.

See docs/superpowers/plans/2026-05-13-extraction-cache-db-overview.md for the
two-level cache architecture this is part of.
"""

CREATE_EXTRACTIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS extractions (
  company         TEXT NOT NULL,
  period_end      TEXT NOT NULL,
  market          TEXT NOT NULL,
  report_type     TEXT NOT NULL,
  catalog_version TEXT NOT NULL,
  schema_version  TEXT NOT NULL,
  generated_at    TEXT NOT NULL,
  artifact_path   TEXT NOT NULL,
  llm_provider    TEXT,
  llm_model       TEXT,
  PRIMARY KEY (company, period_end, market, catalog_version)
);
""".strip()

CREATE_FIELD_VALUES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS field_values (
  company             TEXT NOT NULL,
  period_end          TEXT NOT NULL,
  field_id            TEXT NOT NULL,
  bucket              TEXT NOT NULL,
  value               TEXT,
  currency            TEXT,
  unit                TEXT,
  selected_source     TEXT,
  evidence_page       INTEGER,
  llm_confidence      REAL,
  llm_reasoning_short TEXT,
  PRIMARY KEY (company, period_end, field_id),
  FOREIGN KEY (company, period_end)
    REFERENCES extractions(company, period_end)
);
""".strip()

CREATE_FIELD_VALUES_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_field_values_field
  ON field_values(field_id);
CREATE INDEX IF NOT EXISTS idx_field_values_bucket
  ON field_values(bucket);
""".strip()
```

- [ ] **Step 1.5: Run test to verify it passes**

```bash
uv run pytest tests/cache/test_db_schema.py -v
```

Expected: 3 passed.

- [ ] **Step 1.6: Run ruff + mypy**

```bash
uv run ruff check src/financial_report_llm_extractor/cache tests/cache
uv run mypy src/financial_report_llm_extractor/cache
```

Expected: clean.

- [ ] **Step 1.7: Commit**

```bash
git add src/financial_report_llm_extractor/cache/__init__.py \
        src/financial_report_llm_extractor/cache/db_schema.py \
        tests/cache/__init__.py \
        tests/cache/test_db_schema.py
git commit -m "feat: r1 cache module skeleton + ddl constants"
```

---

## Task 2: `init_db()` connection helper

**Files:**
- Create: `src/financial_report_llm_extractor/cache/db.py`
- Test: `tests/cache/test_db.py`

- [ ] **Step 2.1: Write the failing test**

Write `tests/cache/test_db.py`:

```python
"""init_db() creates tables + indexes."""

import sqlite3
from pathlib import Path

from financial_report_llm_extractor.cache.db import init_db


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
        assert "idx_field_values_field" in indexes
        assert "idx_field_values_bucket" in indexes
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
```

- [ ] **Step 2.2: Run test to verify it fails**

```bash
uv run pytest tests/cache/test_db.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'financial_report_llm_extractor.cache.db'`.

- [ ] **Step 2.3: Implement `db.py`**

Write `src/financial_report_llm_extractor/cache/db.py`:

```python
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
    """Open a connection. Caller is responsible for closing."""
    return sqlite3.connect(db_path, timeout=10.0)
```

- [ ] **Step 2.4: Run test to verify it passes**

```bash
uv run pytest tests/cache/test_db.py -v
```

Expected: 4 passed.

- [ ] **Step 2.5: Run ruff + mypy**

```bash
uv run ruff check src/financial_report_llm_extractor/cache tests/cache
uv run mypy src/financial_report_llm_extractor/cache
```

Expected: clean.

- [ ] **Step 2.6: Commit**

```bash
git add src/financial_report_llm_extractor/cache/db.py tests/cache/test_db.py
git commit -m "feat: r1 init_db() + connect() helpers"
```

---

## Task 3: `index_run()` reads `evaluation.json` and UPSERTs rows

**Files:**
- Create: `src/financial_report_llm_extractor/cache/indexer.py`
- Create: `tests/cache/fixtures/sample_run_minimal/evaluation.json`
- Test: `tests/cache/test_indexer.py`

- [ ] **Step 3.1: Create fixture `evaluation.json`**

Write `tests/cache/fixtures/sample_run_minimal/evaluation.json`:

```json
{
  "company": "600519",
  "period_end": "2024-12-31",
  "market": "CN",
  "report_type": "annual",
  "generated_at": "2026-05-13T10:00:00",
  "schema_version": "evaluation_v1",
  "summary": {
    "by_bucket": {
      "clean_present": 1,
      "llm_supplement_present": 1,
      "unresolved_conflict": 0,
      "terminal_unverified": 0,
      "not_in_scope": 0,
      "source_unavailable": 0
    },
    "total_fields": 2
  },
  "fields": {
    "revenue": {
      "bucket": "clean_present",
      "value": 174144,
      "currency": "CNY",
      "unit": "million",
      "selected_source": "akshare"
    },
    "audit_opinion": {
      "bucket": "llm_supplement_present",
      "value": "standard unqualified opinion",
      "selected_source": "llm",
      "llm_confidence": 0.96,
      "llm_page": 55,
      "llm_reasoning": "Auditor explicitly stated standard unqualified opinion on page 55."
    }
  }
}
```

- [ ] **Step 3.2: Write the failing test**

Write `tests/cache/test_indexer.py`:

```python
"""Round-trip: evaluation.json → DB → SELECT."""

import sqlite3
from pathlib import Path

from financial_report_llm_extractor.cache.db import init_db
from financial_report_llm_extractor.cache.indexer import index_run

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "sample_run_minimal"


def test_index_run_inserts_extractions_row(tmp_path: Path) -> None:
    db_path = tmp_path / "extracted.db"
    init_db(db_path)
    index_run(
        run_dir=FIXTURE_DIR,
        db_path=db_path,
        catalog_version="2026-05-02",
    )
    conn = sqlite3.connect(db_path)
    try:
        rows = list(
            conn.execute(
                "SELECT company, period_end, market, report_type, "
                "catalog_version, llm_provider, llm_model "
                "FROM extractions"
            )
        )
    finally:
        conn.close()
    assert len(rows) == 1
    assert rows[0] == (
        "600519", "2024-12-31", "CN", "annual", "2026-05-02", None, None
    )


def test_index_run_inserts_field_values_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "extracted.db"
    init_db(db_path)
    index_run(
        run_dir=FIXTURE_DIR,
        db_path=db_path,
        catalog_version="2026-05-02",
    )
    conn = sqlite3.connect(db_path)
    try:
        rows = {
            r[0]: r
            for r in conn.execute(
                "SELECT field_id, bucket, value, currency, unit, "
                "selected_source, evidence_page, llm_confidence "
                "FROM field_values"
            )
        }
    finally:
        conn.close()
    assert set(rows) == {"revenue", "audit_opinion"}
    assert rows["revenue"][1] == "clean_present"
    assert rows["revenue"][3] == "CNY"
    assert rows["audit_opinion"][1] == "llm_supplement_present"
    assert rows["audit_opinion"][6] == 55  # evidence_page from llm_page
    assert rows["audit_opinion"][7] == 0.96


def test_index_run_upsert_overwrites(tmp_path: Path) -> None:
    """Indexing same run dir twice must not duplicate rows."""
    db_path = tmp_path / "extracted.db"
    init_db(db_path)
    index_run(run_dir=FIXTURE_DIR, db_path=db_path, catalog_version="v1")
    index_run(run_dir=FIXTURE_DIR, db_path=db_path, catalog_version="v1")
    conn = sqlite3.connect(db_path)
    try:
        ext_count = conn.execute(
            "SELECT COUNT(*) FROM extractions"
        ).fetchone()[0]
        fv_count = conn.execute(
            "SELECT COUNT(*) FROM field_values"
        ).fetchone()[0]
    finally:
        conn.close()
    assert ext_count == 1
    assert fv_count == 2


def test_index_run_different_catalog_versions_coexist(tmp_path: Path) -> None:
    db_path = tmp_path / "extracted.db"
    init_db(db_path)
    index_run(run_dir=FIXTURE_DIR, db_path=db_path, catalog_version="v1")
    index_run(run_dir=FIXTURE_DIR, db_path=db_path, catalog_version="v2")
    conn = sqlite3.connect(db_path)
    try:
        ext_count = conn.execute(
            "SELECT COUNT(*) FROM extractions"
        ).fetchone()[0]
    finally:
        conn.close()
    assert ext_count == 2  # one row per catalog_version
```

- [ ] **Step 3.3: Run test to verify it fails**

```bash
uv run pytest tests/cache/test_indexer.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'financial_report_llm_extractor.cache.indexer'`.

- [ ] **Step 3.4: Implement `indexer.py`**

Write `src/financial_report_llm_extractor/cache/indexer.py`:

```python
"""Index a single evaluate-company run directory into the extraction DB.

Reads evaluation.json from the run dir and UPSERTs one extractions row
plus N field_values rows into the SQLite DB.

The catalog_version comes from the caller (read from the taxonomy file's
`version` field) rather than from the run dir itself, because evaluation.json
does not record which catalog version produced it. Callers should pass the
catalog version that was in effect when the run was generated.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from financial_report_llm_extractor.cache.db import connect


def index_run(
    *,
    run_dir: Path,
    db_path: Path,
    catalog_version: str,
) -> int:
    """Index the given run directory into the DB.

    Returns the number of field rows written.
    Raises FileNotFoundError if run_dir/evaluation.json does not exist.
    """
    eval_path = run_dir / "evaluation.json"
    if not eval_path.exists():
        raise FileNotFoundError(f"no evaluation.json under {run_dir}")
    payload = json.loads(eval_path.read_text(encoding="utf-8"))

    company = str(payload["company"])
    period_end = str(payload["period_end"])
    market = str(payload["market"])
    report_type = str(payload.get("report_type", "annual"))
    schema_version = str(payload.get("schema_version", "evaluation_v1"))
    generated_at = str(payload.get("generated_at", ""))

    fields: dict[str, dict[str, Any]] = payload.get("fields", {})

    conn = connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO extractions (
              company, period_end, market, report_type,
              catalog_version, schema_version, generated_at,
              artifact_path, llm_provider, llm_model
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(company, period_end, market, catalog_version)
            DO UPDATE SET
              schema_version = excluded.schema_version,
              generated_at   = excluded.generated_at,
              artifact_path  = excluded.artifact_path,
              llm_provider   = excluded.llm_provider,
              llm_model      = excluded.llm_model
            """,
            (
                company, period_end, market, report_type,
                catalog_version, schema_version, generated_at,
                str(run_dir), None, None,
            ),
        )

        # field_values: replace all rows for this (company, period_end)
        conn.execute(
            "DELETE FROM field_values WHERE company = ? AND period_end = ?",
            (company, period_end),
        )
        written = 0
        for field_id, info in fields.items():
            value = info.get("value")
            value_text: str | None = (
                None if value is None else json.dumps(value, ensure_ascii=False)
            )
            conn.execute(
                """
                INSERT INTO field_values (
                  company, period_end, field_id, bucket, value,
                  currency, unit, selected_source, evidence_page,
                  llm_confidence, llm_reasoning_short
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    company,
                    period_end,
                    field_id,
                    str(info.get("bucket", "")),
                    value_text,
                    info.get("currency"),
                    info.get("unit"),
                    info.get("selected_source"),
                    info.get("llm_page") or info.get("evidence_page"),
                    info.get("llm_confidence"),
                    _truncate(info.get("llm_reasoning"), 500),
                ),
            )
            written += 1
        conn.commit()
        return written
    finally:
        conn.close()


def _truncate(text: object, max_chars: int) -> str | None:
    if text is None:
        return None
    s = str(text)
    return s if len(s) <= max_chars else s[: max_chars - 1] + "…"
```

- [ ] **Step 3.5: Run test to verify it passes**

```bash
uv run pytest tests/cache/test_indexer.py -v
```

Expected: 4 passed.

- [ ] **Step 3.6: Run ruff + mypy**

```bash
uv run ruff check src/financial_report_llm_extractor/cache tests/cache
uv run mypy src/financial_report_llm_extractor/cache
```

Expected: clean.

- [ ] **Step 3.7: Commit**

```bash
git add src/financial_report_llm_extractor/cache/indexer.py \
        tests/cache/test_indexer.py \
        tests/cache/fixtures/sample_run_minimal/evaluation.json
git commit -m "feat: r1 index_run() upserts evaluation.json into db"
```

---

## Task 4: `query()` read-side API

**Files:**
- Create: `src/financial_report_llm_extractor/cache/db_query.py`
- Test: `tests/cache/test_db_query.py`

- [ ] **Step 4.1: Write the failing test**

Write `tests/cache/test_db_query.py`:

```python
"""Read-side queries: single field, single company, bulk."""

from pathlib import Path

from financial_report_llm_extractor.cache.db import init_db
from financial_report_llm_extractor.cache.db_query import (
    query_field,
    query_extraction,
    list_companies,
)
from financial_report_llm_extractor.cache.indexer import index_run

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "sample_run_minimal"


def _setup(tmp_path: Path) -> Path:
    db_path = tmp_path / "extracted.db"
    init_db(db_path)
    index_run(run_dir=FIXTURE_DIR, db_path=db_path, catalog_version="v1")
    return db_path


def test_query_field_hit(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    result = query_field(
        db_path=db_path,
        company="600519",
        period_end="2024-12-31",
        field_id="revenue",
    )
    assert result is not None
    assert result["bucket"] == "clean_present"
    assert result["value"] == 174144
    assert result["currency"] == "CNY"


def test_query_field_miss_returns_none(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    assert query_field(
        db_path=db_path,
        company="600519",
        period_end="2024-12-31",
        field_id="does_not_exist",
    ) is None


def test_query_extraction_returns_metadata_and_fields(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    result = query_extraction(
        db_path=db_path,
        company="600519",
        period_end="2024-12-31",
    )
    assert result is not None
    assert result["company"] == "600519"
    assert result["market"] == "CN"
    assert "fields" in result
    assert set(result["fields"]) == {"revenue", "audit_opinion"}


def test_list_companies(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    rows = list_companies(db_path=db_path)
    assert ("600519", "2024-12-31", "CN", "v1") in rows
```

- [ ] **Step 4.2: Run test to verify it fails**

```bash
uv run pytest tests/cache/test_db_query.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4.3: Implement `db_query.py`**

Write `src/financial_report_llm_extractor/cache/db_query.py`:

```python
"""Read-side queries against the extraction cache DB."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from financial_report_llm_extractor.cache.db import connect


def query_field(
    *,
    db_path: Path,
    company: str,
    period_end: str,
    field_id: str,
) -> dict[str, Any] | None:
    """Return one field row as a dict, or None on miss."""
    conn = connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT bucket, value, currency, unit, selected_source,
                   evidence_page, llm_confidence, llm_reasoning_short
            FROM field_values
            WHERE company = ? AND period_end = ? AND field_id = ?
            """,
            (company, period_end, field_id),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {
        "company": company,
        "period_end": period_end,
        "field_id": field_id,
        "bucket": row[0],
        "value": json.loads(row[1]) if row[1] is not None else None,
        "currency": row[2],
        "unit": row[3],
        "selected_source": row[4],
        "evidence_page": row[5],
        "llm_confidence": row[6],
        "llm_reasoning_short": row[7],
    }


def query_extraction(
    *,
    db_path: Path,
    company: str,
    period_end: str,
) -> dict[str, Any] | None:
    """Return extraction metadata + all field rows as a nested dict."""
    conn = connect(db_path)
    try:
        meta = conn.execute(
            """
            SELECT market, report_type, catalog_version, schema_version,
                   generated_at, artifact_path, llm_provider, llm_model
            FROM extractions
            WHERE company = ? AND period_end = ?
            ORDER BY catalog_version DESC
            LIMIT 1
            """,
            (company, period_end),
        ).fetchone()
        if meta is None:
            return None
        field_rows = list(
            conn.execute(
                """
                SELECT field_id, bucket, value, currency, unit,
                       selected_source, evidence_page, llm_confidence,
                       llm_reasoning_short
                FROM field_values
                WHERE company = ? AND period_end = ?
                """,
                (company, period_end),
            )
        )
    finally:
        conn.close()
    fields: dict[str, dict[str, Any]] = {}
    for r in field_rows:
        fields[r[0]] = {
            "bucket": r[1],
            "value": json.loads(r[2]) if r[2] is not None else None,
            "currency": r[3],
            "unit": r[4],
            "selected_source": r[5],
            "evidence_page": r[6],
            "llm_confidence": r[7],
            "llm_reasoning_short": r[8],
        }
    return {
        "company": company,
        "period_end": period_end,
        "market": meta[0],
        "report_type": meta[1],
        "catalog_version": meta[2],
        "schema_version": meta[3],
        "generated_at": meta[4],
        "artifact_path": meta[5],
        "llm_provider": meta[6],
        "llm_model": meta[7],
        "fields": fields,
    }


def list_companies(*, db_path: Path) -> list[tuple[str, str, str, str]]:
    """Return list of (company, period_end, market, catalog_version) tuples."""
    conn = connect(db_path)
    try:
        return [
            (r[0], r[1], r[2], r[3])
            for r in conn.execute(
                "SELECT company, period_end, market, catalog_version "
                "FROM extractions ORDER BY company, period_end"
            )
        ]
    finally:
        conn.close()
```

- [ ] **Step 4.4: Run test to verify it passes**

```bash
uv run pytest tests/cache/test_db_query.py -v
```

Expected: 4 passed.

- [ ] **Step 4.5: Run ruff + mypy**

```bash
uv run ruff check src/financial_report_llm_extractor/cache tests/cache
uv run mypy src/financial_report_llm_extractor/cache
```

Expected: clean.

- [ ] **Step 4.6: Commit**

```bash
git add src/financial_report_llm_extractor/cache/db_query.py \
        tests/cache/test_db_query.py
git commit -m "feat: r1 db_query helpers (query_field/query_extraction/list_companies)"
```

---

## Task 5: `index` CLI subcommand

**Files:**
- Modify: `src/financial_report_llm_extractor/cli.py`
- Test: `tests/test_cli.py` (extend)

- [ ] **Step 5.1: Write the failing test**

Append to `tests/test_cli.py`:

```python
def test_cli_index_command_scans_runs_dir(tmp_path: Path) -> None:
    """`index` subcommand walks runs dir + writes DB."""
    import json as _json
    from financial_report_llm_extractor.cli import main

    # Build minimal run dir
    run_dir = tmp_path / "runs" / "600519_2024-12-31"
    run_dir.mkdir(parents=True)
    (run_dir / "evaluation.json").write_text(
        _json.dumps({
            "company": "600519",
            "period_end": "2024-12-31",
            "market": "CN",
            "report_type": "annual",
            "generated_at": "2026-05-13T10:00:00",
            "schema_version": "evaluation_v1",
            "fields": {"revenue": {"bucket": "clean_present", "value": 1}},
        }),
        encoding="utf-8",
    )
    # Build a tiny taxonomy file so the CLI can read catalog_version
    tax_path = tmp_path / "tax.json"
    tax_path.write_text('{"version": "test-1", "fields": {}}', encoding="utf-8")
    db_path = tmp_path / "out.db"
    exit_code = main([
        "index",
        "--runs", str(tmp_path / "runs"),
        "--db", str(db_path),
        "--taxonomy", str(tax_path),
    ])
    assert exit_code == 0
    assert db_path.exists()

    from financial_report_llm_extractor.cache.db_query import list_companies
    assert ("600519", "2024-12-31", "CN", "test-1") in list_companies(
        db_path=db_path
    )
```

- [ ] **Step 5.2: Run test to verify it fails**

```bash
uv run pytest tests/test_cli.py::test_cli_index_command_scans_runs_dir -v
```

Expected: FAIL with argparse error or similar — `index` subcommand not registered.

- [ ] **Step 5.3: Add `index` subparser**

Modify `src/financial_report_llm_extractor/cli.py`. Find the section where other subparsers are added (search for `subparsers.add_parser(`) and add after the last one:

```python
    index_parser = subparsers.add_parser("index")
    index_parser.add_argument("--runs", type=Path, required=True,
                              help="Directory containing per-company run subdirs")
    index_parser.add_argument("--db", type=Path, required=True,
                              help="SQLite DB path to create/update")
    index_parser.add_argument(
        "--taxonomy", type=Path,
        default=Path("field_catalog/turtle_v015_field_taxonomy.json"),
        help="Taxonomy JSON to read catalog_version from",
    )
```

In the `main()` dispatch block (search for `if args.command == "ingest":` style branches), add:

```python
    if args.command == "index":
        from financial_report_llm_extractor.cache.db import init_db as _init_db
        from financial_report_llm_extractor.cache.indexer import (
            index_run as _index_run,
        )
        catalog_version = json.loads(
            args.taxonomy.read_text(encoding="utf-8")
        )["version"]
        _init_db(args.db)
        count_runs = 0
        count_fields = 0
        for sub in sorted(args.runs.iterdir()):
            if not sub.is_dir() or not (sub / "evaluation.json").exists():
                continue
            count_fields += _index_run(
                run_dir=sub, db_path=args.db,
                catalog_version=str(catalog_version),
            )
            count_runs += 1
        print(json.dumps({
            "indexed_runs": count_runs,
            "indexed_fields": count_fields,
            "db": str(args.db),
        }, indent=2, sort_keys=True))
        return 0
```

(Note: `json` and `Path` are already imported at the top of `cli.py`; verify before adding to imports.)

- [ ] **Step 5.4: Run test to verify it passes**

```bash
uv run pytest tests/test_cli.py::test_cli_index_command_scans_runs_dir -v
```

Expected: 1 passed.

- [ ] **Step 5.5: Run full suite + ruff + mypy**

```bash
uv run pytest -q
uv run ruff check .
uv run mypy src tests
```

Expected: all green; no regression in 630+ existing tests.

- [ ] **Step 5.6: Commit**

```bash
git add src/financial_report_llm_extractor/cli.py tests/test_cli.py
git commit -m "feat: r1 cli index command — scan tmp/runs/* into db"
```

---

## Task 6: `query` CLI subcommand

**Files:**
- Modify: `src/financial_report_llm_extractor/cli.py`
- Test: `tests/test_cli.py` (extend)

- [ ] **Step 6.1: Write the failing test**

Append to `tests/test_cli.py`:

```python
def test_cli_query_command_returns_field_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`query --field` outputs single field row as JSON."""
    import json as _json
    from financial_report_llm_extractor.cli import main

    # Seed DB via index
    run_dir = tmp_path / "runs" / "600519_2024-12-31"
    run_dir.mkdir(parents=True)
    (run_dir / "evaluation.json").write_text(
        _json.dumps({
            "company": "600519",
            "period_end": "2024-12-31",
            "market": "CN",
            "report_type": "annual",
            "generated_at": "2026-05-13T10:00:00",
            "schema_version": "evaluation_v1",
            "fields": {
                "revenue": {
                    "bucket": "clean_present", "value": 174144,
                    "currency": "CNY", "unit": "million",
                }
            },
        }),
        encoding="utf-8",
    )
    tax_path = tmp_path / "tax.json"
    tax_path.write_text('{"version": "v1", "fields": {}}', encoding="utf-8")
    db_path = tmp_path / "out.db"
    main([
        "index", "--runs", str(tmp_path / "runs"),
        "--db", str(db_path), "--taxonomy", str(tax_path),
    ])
    capsys.readouterr()  # discard index output

    exit_code = main([
        "query",
        "--db", str(db_path),
        "--company", "600519",
        "--period", "2024-12-31",
        "--field", "revenue",
    ])
    assert exit_code == 0
    captured = capsys.readouterr()
    body = _json.loads(captured.out)
    assert body["field_id"] == "revenue"
    assert body["value"] == 174144
    assert body["currency"] == "CNY"


def test_cli_query_command_without_field_returns_full_extraction(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`query` without --field returns extraction metadata + all fields."""
    import json as _json
    from financial_report_llm_extractor.cli import main

    run_dir = tmp_path / "runs" / "600519_2024-12-31"
    run_dir.mkdir(parents=True)
    (run_dir / "evaluation.json").write_text(
        _json.dumps({
            "company": "600519", "period_end": "2024-12-31",
            "market": "CN", "report_type": "annual",
            "generated_at": "2026-05-13T10:00:00",
            "schema_version": "evaluation_v1",
            "fields": {
                "revenue": {"bucket": "clean_present", "value": 1},
                "net_profit": {"bucket": "clean_present", "value": 2},
            },
        }),
        encoding="utf-8",
    )
    tax_path = tmp_path / "tax.json"
    tax_path.write_text('{"version": "v1", "fields": {}}', encoding="utf-8")
    db_path = tmp_path / "out.db"
    main(["index", "--runs", str(tmp_path / "runs"),
          "--db", str(db_path), "--taxonomy", str(tax_path)])
    capsys.readouterr()

    main([
        "query", "--db", str(db_path),
        "--company", "600519", "--period", "2024-12-31",
    ])
    body = _json.loads(capsys.readouterr().out)
    assert body["company"] == "600519"
    assert set(body["fields"]) == {"revenue", "net_profit"}
```

- [ ] **Step 6.2: Run test to verify it fails**

```bash
uv run pytest tests/test_cli.py::test_cli_query_command_returns_field_json -v
```

Expected: FAIL — `query` subcommand not registered.

- [ ] **Step 6.3: Add `query` subparser**

Modify `src/financial_report_llm_extractor/cli.py`. After the `index_parser` block, add:

```python
    query_parser = subparsers.add_parser("query")
    query_parser.add_argument("--db", type=Path, required=True,
                              help="SQLite DB path")
    query_parser.add_argument("--company", type=str, required=True)
    query_parser.add_argument("--period", type=str, required=True,
                              help="period_end like '2024-12-31'")
    query_parser.add_argument("--field", type=str, default=None,
                              help="Optional field_id; omit for full extraction")
```

In the dispatch block in `main()`, add:

```python
    if args.command == "query":
        from financial_report_llm_extractor.cache.db_query import (
            query_extraction as _query_extraction,
            query_field as _query_field,
        )
        if args.field is not None:
            result: object = _query_field(
                db_path=args.db, company=args.company,
                period_end=args.period, field_id=args.field,
            )
        else:
            result = _query_extraction(
                db_path=args.db, company=args.company,
                period_end=args.period,
            )
        if result is None:
            print(json.dumps({"miss": True}, sort_keys=True))
            return 1
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
        return 0
```

- [ ] **Step 6.4: Run tests to verify they pass**

```bash
uv run pytest tests/test_cli.py::test_cli_query_command_returns_field_json \
              tests/test_cli.py::test_cli_query_command_without_field_returns_full_extraction \
              -v
```

Expected: 2 passed.

- [ ] **Step 6.5: Run full suite + ruff + mypy**

```bash
uv run pytest -q
uv run ruff check .
uv run mypy src tests
```

Expected: all green.

- [ ] **Step 6.6: Commit**

```bash
git add src/financial_report_llm_extractor/cli.py tests/test_cli.py
git commit -m "feat: r1 cli query command — read field/extraction from db"
```

---

## Task 7: Update CLAUDE.md + phase-summary pointer

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/2026-05-11-phase-summary.md`

- [ ] **Step 7.1: Add cache module pointer to CLAUDE.md**

In `CLAUDE.md`, find the "分阶段模块" table (search for `| 阶段 | 模块 | 职责 |`). Add a new row before the closing of the table (or after the last row matching the latest phase):

```markdown
| R1 | `cache/db_schema.py` + `db.py` + `indexer.py` + `db_query.py` | Two-level extraction cache layer-1: SQLite DB at `data/extracted.db` indexed from `tmp/runs/*/evaluation.json`. New CLI `index` + `query` commands. Zero pipeline behavior change. See `docs/superpowers/plans/2026-05-13-extraction-cache-db-overview.md`. |
```

- [ ] **Step 7.2: Add §6 entry to phase-summary**

In `docs/2026-05-11-phase-summary.md`, find the §6 unresolved-items table. Add a new row noting R1 complete:

```markdown
| **R1 SQLite indexer (`data/extracted.db`)** | **已落地 (2026-05-13)** | R1 plan | New `cache/` module + `index` / `query` CLI commands. Indexes existing `tmp/runs/*/evaluation.json` into DB. Pipeline behavior unchanged. R2 (provider fetch cache) + R3 (LLM cache) + R4 (DB-aware `pipeline` command) follow in separate PRs. |
```

- [ ] **Step 7.3: Run full verification**

```bash
uv run pytest -q
uv run ruff check .
uv run mypy src tests
```

Expected: all green.

- [ ] **Step 7.4: Commit**

```bash
git add CLAUDE.md docs/2026-05-11-phase-summary.md
git commit -m "docs: r1 sqlite indexer pointer in claude.md + phase-summary"
```

---

## Acceptance Criteria

After all 7 tasks complete:

- [ ] `uv run pytest -q` shows 7+ new tests passing, no regressions in existing 630+ tests
- [ ] `uv run ruff check .` clean
- [ ] `uv run mypy src tests` clean
- [ ] `uv run financial-report-llm-extractor index --runs tmp/runs --db data/extracted.db` produces a non-empty DB
- [ ] `uv run financial-report-llm-extractor query --db data/extracted.db --company 600519 --period 2024-12-31 --field revenue` returns JSON with the expected value
- [ ] No new files outside `src/financial_report_llm_extractor/cache/`, `tests/cache/`, `docs/superpowers/plans/`, plus surgical edits to `cli.py`, `CLAUDE.md`, `docs/2026-05-11-phase-summary.md`, `tests/test_cli.py`
- [ ] No new entries in `pyproject.toml` `dependencies` (stdlib only)
- [ ] CLAUDE.md "分阶段模块" table references the R1 module
- [ ] Phase-summary §6 lists R1 as complete with date

## Self-Review

- [x] **Spec coverage**: every section in the overview doc's "R1: SQLite Indexer" sub-section is covered by a task. The overview lists `db_schema.py`, `db.py`, `indexer.py`, `db_query.py`, `index` CLI, `query` CLI — all 6 produced by tasks 1-6. Task 7 closes the documentation loop.
- [x] **Placeholder scan**: every step has complete code or exact command. No "TBD" / "implement later" / "add validation". Test inputs and expected outputs are concrete.
- [x] **Type consistency**: function signatures match across tasks. `init_db(db_path: Path)`, `connect(db_path: Path)`, `index_run(*, run_dir, db_path, catalog_version)`, `query_field(*, db_path, company, period_end, field_id)`. CLI dispatch references the same names.
- [x] **No referenced symbols undefined**: `connect()` defined in task 2 used by tasks 3 and 4. `init_db()` defined in task 2 used by tasks 3-6 tests and CLI. `_truncate()` is local to `indexer.py`. All type imports (`Path`, `Any`, `json`) are stdlib.
