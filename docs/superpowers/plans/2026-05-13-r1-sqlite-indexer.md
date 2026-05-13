# R1 SQLite Indexer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a SQLite indexer that scans `tmp/runs/*/{evaluation.json, llm_evidence_supplement.json}` and writes canonical extraction results to `data/extracted.db`, plus `query` CLI command for cross-cohort queries. Zero behavior change to the existing pipeline; this is purely additive.

**Architecture:** New `cache/` sub-package parallel to `structured_sources/`. Read-only with respect to the pipeline: only consumes existing artifacts. Reads two files per run and joins by `field_id` because `evaluation.json.fields[].value` is `null` for `llm_supplement_present` buckets (the actual value, page, confidence, and reasoning live in `llm_evidence_supplement.json.items[field_id]`). Uses stdlib `sqlite3`, no new dependencies. Catalog version forms part of the `extractions` primary key.

**Tech Stack:** Python 3.11 stdlib (`sqlite3`, `json`, `pathlib`), pytest, project's existing CLI argparse pattern.

---

## Data-Source Audit (why two files)

Inspection of actual `tmp/runs/600519_codex_gpt55/`:

| Field | bucket in `evaluation.json` | `evaluation.json.fields[fid].value` | `llm_evidence_supplement.json.items[fid].value` |
|---|---|---|---|
| `revenue` | `clean_present` | `"170899152276.34"` (string-encoded number from akshare) | (not present in supplement) |
| `audit_opinion` | `llm_supplement_present` | **`null`** | `"标准无保留意见..."` + `page: 55`, `confidence: 0.98`, `reasoning: "审计报告..."` |

So:
- For `bucket in {clean_present, unresolved_conflict, source_unavailable, terminal_unverified, not_in_scope}` → value/currency/unit/selected_source come from `evaluation.json`.
- For `bucket == llm_supplement_present` → metadata still comes from `evaluation.json` (bucket, currency from `evaluation.json` may already be `"unknown"` for LLM); **value/page/confidence/reasoning come from `llm_evidence_supplement.json.items[fid]`**.

The indexer must join both files by `field_id` and pick the right source per bucket.

---

## File Structure

| File | Role |
|---|---|
| `src/financial_report_llm_extractor/cache/__init__.py` | Package marker |
| `src/financial_report_llm_extractor/cache/db_schema.py` | DDL constants for `extractions` + `field_values` tables |
| `src/financial_report_llm_extractor/cache/db.py` | `init_db()`, `connect()` helpers |
| `src/financial_report_llm_extractor/cache/indexer.py` | `index_run(run_dir, db_path, catalog_version, priority_map)` |
| `src/financial_report_llm_extractor/cache/db_query.py` | `query_field`, `query_extraction`, `list_companies` |
| `src/financial_report_llm_extractor/cli.py` | Add `index` + `query` subcommands |
| `tests/test_cache_db_schema.py` | DDL constants present + parseable |
| `tests/test_cache_db.py` | `init_db()` creates tables |
| `tests/test_cache_indexer.py` | Two-file fixture → DB round-trip |
| `tests/test_cache_db_query.py` | Query single + bulk |
| `tests/test_cli.py` (extend) | CLI integration for `index` + `query` |
| `tests/fixtures/cache_sample_run/evaluation.json` | Realistic fixture (clean + llm field) |
| `tests/fixtures/cache_sample_run/llm_evidence_supplement.json` | Companion fixture |

Test files are flat under `tests/` per project convention (no `tests/cache/` subdir; `tests/fixtures/` is the only `tests/` subdir, holding all fixtures).

---

## Key Design Decisions

1. **`field_values` is "latest-catalog-version only" for a given (company, period_end).** Multiple catalog versions can coexist in `extractions` (history of runs) but `field_values` is replaced on every index. Reason: downstream queries "give me 600519/2024 revenue" want the latest answer, not version-specific history.
2. **`value` stored as JSON-encoded string** (e.g., `"170899152276.34"` for stringified numbers, `"unqualified opinion"` for text). Caller decodes via `json.loads()` then knows from `field_id` / context whether to `Decimal()` or use as string.
3. **`catalog_version` is auto-detected from `evaluation.json.catalog_version` if present, else from `--taxonomy` flag at index time (with a stderr warning).** Forward-compat with R4 which will start writing `catalog_version` into `evaluation.json`. Existing 80+ historical runs without that field get labeled with the current taxonomy version + a clear warning. Caller can override via `--catalog-version` flag.
4. **`priority` is denormalized into `field_values`** to allow `WHERE priority='P0'` queries without joining the taxonomy file at query time. Built by CLI from taxonomy at index time.
5. **No `reason` column in `extractions`; `reason` per-field goes in `field_values`** (it's an `evaluation.json.fields[fid].reason` value).

---

## SQLite Schema (final)

```sql
CREATE TABLE IF NOT EXISTS extractions (
  company         TEXT NOT NULL,
  period_end      TEXT NOT NULL,        -- e.g., '2024-12-31'
  market          TEXT NOT NULL,        -- CN / HK
  report_type     TEXT NOT NULL,        -- annual / semi_annual / quarterly
  catalog_version TEXT NOT NULL,        -- 'unknown' or taxonomy version
  schema_version  TEXT NOT NULL,        -- evaluation.json schema_version
  generated_at    TEXT NOT NULL,
  artifact_path   TEXT NOT NULL,        -- relative path to tmp/runs/<cid>_<period>/
  llm_provider    TEXT,
  llm_model       TEXT,
  PRIMARY KEY (company, period_end, market, catalog_version)
);

CREATE TABLE IF NOT EXISTS field_values (
  company             TEXT NOT NULL,
  period_end          TEXT NOT NULL,
  field_id            TEXT NOT NULL,
  priority            TEXT,             -- P0 / P1 / P2 / P3 / P4 (denormalized)
  bucket              TEXT NOT NULL,
  value               TEXT,             -- JSON-encoded scalar
  currency            TEXT,
  unit                TEXT,
  selected_source     TEXT,
  reason              TEXT,             -- e.g., 'missing_source_candidate'
  evidence_page       INTEGER,
  llm_confidence      REAL,
  llm_reasoning_short TEXT,
  PRIMARY KEY (company, period_end, field_id),
  FOREIGN KEY (company, period_end)
    REFERENCES extractions(company, period_end)
);

CREATE INDEX IF NOT EXISTS idx_field_values_field    ON field_values(field_id);
CREATE INDEX IF NOT EXISTS idx_field_values_bucket   ON field_values(bucket);
CREATE INDEX IF NOT EXISTS idx_field_values_priority ON field_values(priority);
```

---

## Task 1: Create cache module skeleton + DDL constants

**Files:**
- Create: `src/financial_report_llm_extractor/cache/__init__.py`
- Create: `src/financial_report_llm_extractor/cache/db_schema.py`
- Test: `tests/test_cache_db_schema.py`

- [ ] **Step 1.1: Write the failing test**

Write `tests/test_cache_db_schema.py`:

```python
"""DDL constants for the extraction cache DB."""

from financial_report_llm_extractor.cache import db_schema


def test_extractions_ddl_contains_primary_key() -> None:
    sql = db_schema.CREATE_EXTRACTIONS_TABLE_SQL
    assert "CREATE TABLE" in sql
    assert "extractions" in sql
    assert "PRIMARY KEY" in sql
    for col in ("company", "period_end", "market", "catalog_version"):
        assert col in sql


def test_field_values_ddl_contains_required_columns() -> None:
    sql = db_schema.CREATE_FIELD_VALUES_TABLE_SQL
    assert "CREATE TABLE" in sql
    assert "field_values" in sql
    assert "FOREIGN KEY" in sql
    assert "REFERENCES extractions" in sql
    # Columns introduced in the design review (reason + priority denormalized)
    for col in (
        "bucket", "field_id", "value", "reason", "priority",
        "evidence_page", "llm_confidence", "llm_reasoning_short",
    ):
        assert col in sql, f"missing column {col}"


def test_indexes_present() -> None:
    sql = db_schema.CREATE_FIELD_VALUES_INDEXES_SQL
    for idx in (
        "idx_field_values_field",
        "idx_field_values_bucket",
        "idx_field_values_priority",
    ):
        assert idx in sql, f"missing index {idx}"
```

- [ ] **Step 1.2: Run test to verify it fails**

```bash
uv run pytest tests/test_cache_db_schema.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'financial_report_llm_extractor.cache'`.

- [ ] **Step 1.3: Create cache package skeleton**

Create `src/financial_report_llm_extractor/cache/__init__.py` as an empty file.

- [ ] **Step 1.4: Implement `db_schema.py`**

Write `src/financial_report_llm_extractor/cache/db_schema.py`:

```python
"""SQLite DDL constants for the extraction result cache (Layer 1).

See docs/superpowers/plans/2026-05-13-extraction-cache-db-overview.md for the
two-level cache architecture this is part of.

Schema notes:
- `field_values` is "latest catalog version only" for a given
  (company, period_end). Multiple catalog versions coexist in `extractions`
  (history of runs) but `field_values` rows are replaced on every re-index.
- `value` is JSON-encoded text; numeric fields are stringified (e.g.,
  '"170899152276.34"'), text fields are JSON strings. Caller uses
  `json.loads()` then context to decide on `Decimal`/`float`/`str`.
- `priority` is denormalized from the taxonomy so queries like
  `WHERE priority='P0'` don't need a taxonomy join.
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
  priority            TEXT,
  bucket              TEXT NOT NULL,
  value               TEXT,
  currency            TEXT,
  unit                TEXT,
  selected_source     TEXT,
  reason              TEXT,
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
CREATE INDEX IF NOT EXISTS idx_field_values_priority
  ON field_values(priority);
""".strip()
```

- [ ] **Step 1.5: Run test to verify it passes**

```bash
uv run pytest tests/test_cache_db_schema.py -v
```

Expected: 3 passed.

- [ ] **Step 1.6: Run ruff + mypy**

```bash
uv run ruff check src/financial_report_llm_extractor/cache tests/test_cache_db_schema.py
uv run mypy src/financial_report_llm_extractor/cache
```

Expected: clean.

- [ ] **Step 1.7: Commit**

```bash
git add src/financial_report_llm_extractor/cache/__init__.py \
        src/financial_report_llm_extractor/cache/db_schema.py \
        tests/test_cache_db_schema.py
git commit -m "feat: r1 cache module skeleton + ddl (extractions + field_values + indexes)"
```

---

## Task 2: `init_db()` + `connect()` helpers

**Files:**
- Create: `src/financial_report_llm_extractor/cache/db.py`
- Test: `tests/test_cache_db.py`

- [ ] **Step 2.1: Write the failing test**

Write `tests/test_cache_db.py`:

```python
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
```

- [ ] **Step 2.2: Run test to verify it fails**

```bash
uv run pytest tests/test_cache_db.py -v
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
    """Open a connection with a 10-second busy timeout for soft concurrency."""
    return sqlite3.connect(db_path, timeout=10.0)
```

- [ ] **Step 2.4: Run test to verify it passes**

```bash
uv run pytest tests/test_cache_db.py -v
```

Expected: 5 passed.

- [ ] **Step 2.5: Run ruff + mypy**

```bash
uv run ruff check src/financial_report_llm_extractor/cache tests/test_cache_db.py
uv run mypy src/financial_report_llm_extractor/cache
```

Expected: clean.

- [ ] **Step 2.6: Commit**

```bash
git add src/financial_report_llm_extractor/cache/db.py tests/test_cache_db.py
git commit -m "feat: r1 init_db() + connect() helpers"
```

---

## Task 3: `index_run()` joins evaluation + llm_evidence_supplement

**Files:**
- Create: `src/financial_report_llm_extractor/cache/indexer.py`
- Create: `tests/fixtures/cache_sample_run/evaluation.json`
- Create: `tests/fixtures/cache_sample_run/llm_evidence_supplement.json`
- Test: `tests/test_cache_indexer.py`

- [ ] **Step 3.1: Create realistic two-file fixture**

Write `tests/fixtures/cache_sample_run/evaluation.json` (realistic shape with both bucket types):

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
      "unresolved_conflict": 1,
      "terminal_unverified": 0,
      "not_in_scope": 0,
      "source_unavailable": 0
    },
    "total_fields": 3
  },
  "fields": {
    "revenue": {
      "bucket": "clean_present",
      "value": "170899152276.34",
      "currency": "CNY",
      "unit": "yuan",
      "selected_source": "akshare",
      "reason": null
    },
    "audit_opinion": {
      "bucket": "llm_supplement_present",
      "value": null,
      "currency": "unknown",
      "unit": null,
      "selected_source": "llm",
      "reason": null
    },
    "fix_assets": {
      "bucket": "unresolved_conflict",
      "value": null,
      "currency": "CNY",
      "unit": null,
      "selected_source": null,
      "reason": "missing_source_candidate"
    }
  }
}
```

Write `tests/fixtures/cache_sample_run/llm_evidence_supplement.json`:

```json
{
  "company_id": "600519",
  "pdf_path": "downloads/cn_stocks/600519/annual/2024_年度报告.pdf",
  "extracted_at": "2026-05-13T10:00:00",
  "schema_version": "llm_evidence_v1",
  "items": {
    "audit_opinion": {
      "status": "present",
      "value": "标准无保留意见。",
      "page": 55,
      "confidence": 0.98,
      "currency": null,
      "unit": null,
      "period": "2024年度",
      "reasoning": "审计报告\"一、审计意见\"段落明确表达财务报表在所有重大方面公允反映。",
      "statement_line": "我们认为，后附的财务报表在所有重大方面...",
      "errors": [],
      "parsed_numeric_value": null
    }
  },
  "summary": {
    "items_hit": 1
  }
}
```

- [ ] **Step 3.2: Write the failing test**

Write `tests/test_cache_indexer.py`:

```python
"""Round-trip: evaluation.json + llm_evidence_supplement.json -> DB -> SELECT.

Verifies that index_run correctly joins the two-file inputs by field_id and
picks the value/page/confidence/reasoning from llm_evidence_supplement.json
for llm_supplement_present buckets.
"""

import json
import sqlite3
from pathlib import Path

import pytest

from financial_report_llm_extractor.cache.db import init_db
from financial_report_llm_extractor.cache.indexer import index_run

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "cache_sample_run"

PRIORITY_MAP = {
    "revenue": "P0",
    "audit_opinion": "P4",
    "fix_assets": "P0",
}


def test_index_run_inserts_extractions_row(tmp_path: Path) -> None:
    db_path = tmp_path / "extracted.db"
    init_db(db_path)
    index_run(
        run_dir=FIXTURE_DIR,
        db_path=db_path,
        catalog_version="2026-05-02",
        priority_map=PRIORITY_MAP,
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
    assert rows[0][:5] == ("600519", "2024-12-31", "CN", "annual", "2026-05-02")


def test_index_run_clean_present_value_from_evaluation(tmp_path: Path) -> None:
    """clean_present bucket: value comes from evaluation.json directly."""
    db_path = tmp_path / "extracted.db"
    init_db(db_path)
    index_run(
        run_dir=FIXTURE_DIR, db_path=db_path,
        catalog_version="v1", priority_map=PRIORITY_MAP,
    )
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT bucket, value, currency, unit, selected_source, "
            "priority, reason "
            "FROM field_values WHERE field_id = 'revenue'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row[0] == "clean_present"
    assert json.loads(row[1]) == "170899152276.34"  # JSON-encoded string
    assert row[2] == "CNY"
    assert row[3] == "yuan"
    assert row[4] == "akshare"
    assert row[5] == "P0"
    assert row[6] is None


def test_index_run_llm_bucket_value_from_supplement(tmp_path: Path) -> None:
    """llm_supplement_present bucket: value/page/confidence/reasoning come from
    llm_evidence_supplement.json, NOT evaluation.json (where value is null)."""
    db_path = tmp_path / "extracted.db"
    init_db(db_path)
    index_run(
        run_dir=FIXTURE_DIR, db_path=db_path,
        catalog_version="v1", priority_map=PRIORITY_MAP,
    )
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT bucket, value, evidence_page, llm_confidence, "
            "llm_reasoning_short, priority "
            "FROM field_values WHERE field_id = 'audit_opinion'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row[0] == "llm_supplement_present"
    assert json.loads(row[1]).startswith("标准无保留意见")  # from supplement
    assert row[2] == 55
    assert row[3] == pytest.approx(0.98)
    assert row[4] is not None and "审计意见" in row[4]
    assert row[5] == "P4"


def test_index_run_unresolved_conflict_has_reason(tmp_path: Path) -> None:
    """unresolved_conflict bucket: value is null, reason is preserved."""
    db_path = tmp_path / "extracted.db"
    init_db(db_path)
    index_run(
        run_dir=FIXTURE_DIR, db_path=db_path,
        catalog_version="v1", priority_map=PRIORITY_MAP,
    )
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT bucket, value, reason FROM field_values "
            "WHERE field_id = 'fix_assets'"
        ).fetchone()
    finally:
        conn.close()
    assert row == ("unresolved_conflict", None, "missing_source_candidate")


def test_index_run_returns_field_count(tmp_path: Path) -> None:
    db_path = tmp_path / "extracted.db"
    init_db(db_path)
    n = index_run(
        run_dir=FIXTURE_DIR, db_path=db_path,
        catalog_version="v1", priority_map=PRIORITY_MAP,
    )
    assert n == 3


def test_index_run_upsert_replaces_field_values(tmp_path: Path) -> None:
    """Re-indexing same (company, period_end) replaces field_values atomically."""
    db_path = tmp_path / "extracted.db"
    init_db(db_path)
    index_run(run_dir=FIXTURE_DIR, db_path=db_path,
              catalog_version="v1", priority_map=PRIORITY_MAP)
    index_run(run_dir=FIXTURE_DIR, db_path=db_path,
              catalog_version="v1", priority_map=PRIORITY_MAP)
    conn = sqlite3.connect(db_path)
    try:
        ext_count = conn.execute(
            "SELECT COUNT(*) FROM extractions").fetchone()[0]
        fv_count = conn.execute(
            "SELECT COUNT(*) FROM field_values").fetchone()[0]
    finally:
        conn.close()
    assert ext_count == 1
    assert fv_count == 3


def test_index_run_different_catalog_versions_extractions_coexist(
    tmp_path: Path,
) -> None:
    """Different catalog_versions create separate extractions rows.
    field_values is replaced on every index (latest catalog_version only)."""
    db_path = tmp_path / "extracted.db"
    init_db(db_path)
    index_run(run_dir=FIXTURE_DIR, db_path=db_path,
              catalog_version="v1", priority_map=PRIORITY_MAP)
    index_run(run_dir=FIXTURE_DIR, db_path=db_path,
              catalog_version="v2", priority_map=PRIORITY_MAP)
    conn = sqlite3.connect(db_path)
    try:
        ext_count = conn.execute(
            "SELECT COUNT(*) FROM extractions").fetchone()[0]
        fv_count = conn.execute(
            "SELECT COUNT(*) FROM field_values").fetchone()[0]
    finally:
        conn.close()
    assert ext_count == 2  # two catalog versions in extractions history
    assert fv_count == 3   # field_values still reflects latest catalog only


def test_index_run_missing_evaluation_raises(tmp_path: Path) -> None:
    db_path = tmp_path / "extracted.db"
    init_db(db_path)
    empty_run = tmp_path / "empty_run"
    empty_run.mkdir()
    with pytest.raises(FileNotFoundError):
        index_run(run_dir=empty_run, db_path=db_path,
                  catalog_version="v1", priority_map={})


def test_index_run_missing_supplement_does_not_break(tmp_path: Path) -> None:
    """If llm_evidence_supplement.json is absent, LLM rows have null value but
    the row is still inserted with the bucket from evaluation.json."""
    db_path = tmp_path / "extracted.db"
    init_db(db_path)
    run_dir = tmp_path / "run_no_supplement"
    run_dir.mkdir()
    (run_dir / "evaluation.json").write_text(
        (FIXTURE_DIR / "evaluation.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    n = index_run(
        run_dir=run_dir, db_path=db_path,
        catalog_version="v1", priority_map=PRIORITY_MAP,
    )
    assert n == 3
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT value, evidence_page FROM field_values "
            "WHERE field_id = 'audit_opinion'"
        ).fetchone()
    finally:
        conn.close()
    assert row == (None, None)  # supplement missing -> null
```

- [ ] **Step 3.3: Run test to verify it fails**

```bash
uv run pytest tests/test_cache_indexer.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'financial_report_llm_extractor.cache.indexer'`.

- [ ] **Step 3.4: Implement `indexer.py`**

Write `src/financial_report_llm_extractor/cache/indexer.py`:

```python
"""Index a single evaluate-company run directory into the extraction DB.

Reads BOTH evaluation.json AND llm_evidence_supplement.json from the run dir
and UPSERTs one extractions row plus N field_values rows.

Why two files: evaluation.json carries the bucket assignment and
deterministic (clean_present) values, but for LLM-supplement buckets the
actual value/page/confidence/reasoning live in llm_evidence_supplement.json.
We join by field_id and pick the right source per bucket.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from financial_report_llm_extractor.cache.db import connect


def index_run(
    *,
    run_dir: Path,
    db_path: Path,
    catalog_version: str,
    priority_map: Mapping[str, str],
) -> int:
    """Index the given run directory into the DB.

    Reads run_dir/evaluation.json (required) and run_dir/llm_evidence_supplement.json
    (optional — only LLM buckets need it). Returns the number of field rows
    written.

    Raises FileNotFoundError if evaluation.json does not exist.
    """
    eval_path = run_dir / "evaluation.json"
    if not eval_path.exists():
        raise FileNotFoundError(f"no evaluation.json under {run_dir}")
    payload = json.loads(eval_path.read_text(encoding="utf-8"))

    supplement_items: dict[str, dict[str, Any]] = {}
    supp_path = run_dir / "llm_evidence_supplement.json"
    if supp_path.exists():
        supp_payload = json.loads(supp_path.read_text(encoding="utf-8"))
        items = supp_payload.get("items", {})
        if isinstance(items, dict):
            supplement_items = {
                str(k): v for k, v in items.items() if isinstance(v, dict)
            }

    company = str(payload["company"])
    period_end = str(payload["period_end"])
    market = str(payload["market"])
    report_type = str(payload.get("report_type", "annual"))
    schema_version = str(payload.get("schema_version", "evaluation_v1"))
    generated_at = str(payload.get("generated_at", ""))

    # Forward-compat: prefer catalog_version recorded in evaluation.json
    # (R4 will start writing this); fall back to the explicit argument.
    effective_catalog_version = str(
        payload.get("catalog_version") or catalog_version
    )

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
                effective_catalog_version, schema_version, generated_at,
                str(run_dir), None, None,
            ),
        )

        # field_values is "latest catalog version only" — replace all rows
        # for this (company, period_end) on every index.
        conn.execute(
            "DELETE FROM field_values WHERE company = ? AND period_end = ?",
            (company, period_end),
        )

        written = 0
        for field_id, eval_info in fields.items():
            bucket = str(eval_info.get("bucket", ""))
            supp = supplement_items.get(field_id, {})
            row = _merge_field_row(
                bucket=bucket,
                eval_info=eval_info,
                supplement=supp,
            )
            conn.execute(
                """
                INSERT INTO field_values (
                  company, period_end, field_id, priority, bucket, value,
                  currency, unit, selected_source, reason,
                  evidence_page, llm_confidence, llm_reasoning_short
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    company, period_end, field_id,
                    priority_map.get(field_id),
                    bucket,
                    row["value"],
                    row["currency"],
                    row["unit"],
                    row["selected_source"],
                    row["reason"],
                    row["evidence_page"],
                    row["llm_confidence"],
                    row["llm_reasoning_short"],
                ),
            )
            written += 1
        conn.commit()
        return written
    finally:
        conn.close()


def _merge_field_row(
    *,
    bucket: str,
    eval_info: dict[str, Any],
    supplement: dict[str, Any],
) -> dict[str, Any]:
    """Pick value/page/confidence/reasoning from the right source per bucket.

    - llm_supplement_present: prefer supplement, fall back to evaluation.
    - other buckets: use evaluation directly. Supplement metadata (if any)
      is ignored to avoid mixing LLM-attempt artifacts into deterministic rows.
    """
    eval_value = eval_info.get("value")

    if bucket == "llm_supplement_present":
        value = supplement.get("value") if supplement else eval_value
        page = supplement.get("page")
        confidence = supplement.get("confidence")
        reasoning = supplement.get("reasoning")
        # currency/unit can come from supplement if evaluation has 'unknown'/None
        currency = (
            supplement.get("currency") or eval_info.get("currency") or None
        )
        unit = supplement.get("unit") or eval_info.get("unit") or None
    else:
        value = eval_value
        page = None
        confidence = None
        reasoning = None
        currency = eval_info.get("currency")
        unit = eval_info.get("unit")

    return {
        "value": _json_encode(value),
        "currency": currency if currency != "unknown" else None,
        "unit": unit,
        "selected_source": eval_info.get("selected_source"),
        "reason": eval_info.get("reason"),
        "evidence_page": (
            int(page) if isinstance(page, (int, float)) and page else None
        ),
        "llm_confidence": (
            float(confidence)
            if isinstance(confidence, (int, float)) else None
        ),
        "llm_reasoning_short": _truncate(reasoning, 500),
    }


def _json_encode(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _truncate(text: Any, max_chars: int) -> str | None:
    if text is None:
        return None
    s = str(text)
    return s if len(s) <= max_chars else s[: max_chars - 1] + "…"
```

- [ ] **Step 3.5: Run test to verify it passes**

```bash
uv run pytest tests/test_cache_indexer.py -v
```

Expected: 9 passed.

- [ ] **Step 3.6: Run ruff + mypy**

```bash
uv run ruff check src/financial_report_llm_extractor/cache tests/test_cache_indexer.py
uv run mypy src/financial_report_llm_extractor/cache
```

Expected: clean.

- [ ] **Step 3.7: Commit**

```bash
git add src/financial_report_llm_extractor/cache/indexer.py \
        tests/test_cache_indexer.py \
        tests/fixtures/cache_sample_run/evaluation.json \
        tests/fixtures/cache_sample_run/llm_evidence_supplement.json
git commit -m "feat: r1 index_run() joins evaluation + llm_evidence_supplement by field_id"
```

---

## Task 4: `query()` read-side API

**Files:**
- Create: `src/financial_report_llm_extractor/cache/db_query.py`
- Test: `tests/test_cache_db_query.py`

- [ ] **Step 4.1: Write the failing test**

Write `tests/test_cache_db_query.py`:

```python
"""Read-side queries: single field, single extraction, list companies."""

from pathlib import Path

from financial_report_llm_extractor.cache.db import init_db
from financial_report_llm_extractor.cache.db_query import (
    list_companies,
    query_extraction,
    query_field,
)
from financial_report_llm_extractor.cache.indexer import index_run

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "cache_sample_run"
PRIORITY_MAP = {"revenue": "P0", "audit_opinion": "P4", "fix_assets": "P0"}


def _setup(tmp_path: Path) -> Path:
    db_path = tmp_path / "extracted.db"
    init_db(db_path)
    index_run(
        run_dir=FIXTURE_DIR, db_path=db_path,
        catalog_version="v1", priority_map=PRIORITY_MAP,
    )
    return db_path


def test_query_field_clean_present(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    result = query_field(
        db_path=db_path,
        company="600519", period_end="2024-12-31", field_id="revenue",
    )
    assert result is not None
    assert result["bucket"] == "clean_present"
    assert result["value"] == "170899152276.34"  # decoded from JSON
    assert result["currency"] == "CNY"
    assert result["priority"] == "P0"


def test_query_field_llm_supplement(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    result = query_field(
        db_path=db_path,
        company="600519", period_end="2024-12-31", field_id="audit_opinion",
    )
    assert result is not None
    assert result["bucket"] == "llm_supplement_present"
    assert result["value"].startswith("标准无保留意见")
    assert result["evidence_page"] == 55
    assert result["llm_confidence"] == 0.98
    assert "审计意见" in result["llm_reasoning_short"]


def test_query_field_miss_returns_none(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    assert query_field(
        db_path=db_path, company="600519",
        period_end="2024-12-31", field_id="does_not_exist",
    ) is None


def test_query_extraction_returns_metadata_and_fields(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    result = query_extraction(
        db_path=db_path, company="600519", period_end="2024-12-31",
    )
    assert result is not None
    assert result["company"] == "600519"
    assert result["market"] == "CN"
    assert "fields" in result
    assert set(result["fields"]) == {"revenue", "audit_opinion", "fix_assets"}
    assert result["fields"]["revenue"]["priority"] == "P0"


def test_list_companies(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    rows = list_companies(db_path=db_path)
    assert ("600519", "2024-12-31", "CN", "v1") in rows
```

- [ ] **Step 4.2: Run test to verify it fails**

```bash
uv run pytest tests/test_cache_db_query.py -v
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


_FIELD_COLUMNS = (
    "bucket", "value", "currency", "unit", "selected_source",
    "reason", "evidence_page", "llm_confidence", "llm_reasoning_short",
    "priority",
)


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
            f"SELECT {', '.join(_FIELD_COLUMNS)} "
            "FROM field_values "
            "WHERE company = ? AND period_end = ? AND field_id = ?",
            (company, period_end, field_id),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return _decode_field_row(
        company=company, period_end=period_end, field_id=field_id, row=row,
    )


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
                f"SELECT field_id, {', '.join(_FIELD_COLUMNS)} "
                "FROM field_values "
                "WHERE company = ? AND period_end = ?",
                (company, period_end),
            )
        )
    finally:
        conn.close()
    fields: dict[str, dict[str, Any]] = {}
    for r in field_rows:
        fid = r[0]
        decoded = _decode_field_row(
            company=company, period_end=period_end, field_id=fid, row=r[1:],
        )
        fields[fid] = {k: v for k, v in decoded.items()
                       if k not in {"company", "period_end", "field_id"}}
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


def _decode_field_row(
    *, company: str, period_end: str, field_id: str, row: tuple[Any, ...],
) -> dict[str, Any]:
    (bucket, value_text, currency, unit, selected_source, reason,
     evidence_page, llm_confidence, llm_reasoning_short, priority) = row
    return {
        "company": company,
        "period_end": period_end,
        "field_id": field_id,
        "priority": priority,
        "bucket": bucket,
        "value": json.loads(value_text) if value_text is not None else None,
        "currency": currency,
        "unit": unit,
        "selected_source": selected_source,
        "reason": reason,
        "evidence_page": evidence_page,
        "llm_confidence": llm_confidence,
        "llm_reasoning_short": llm_reasoning_short,
    }
```

- [ ] **Step 4.4: Run test to verify it passes**

```bash
uv run pytest tests/test_cache_db_query.py -v
```

Expected: 5 passed.

- [ ] **Step 4.5: Run ruff + mypy**

```bash
uv run ruff check src/financial_report_llm_extractor/cache tests/test_cache_db_query.py
uv run mypy src/financial_report_llm_extractor/cache
```

Expected: clean.

- [ ] **Step 4.6: Commit**

```bash
git add src/financial_report_llm_extractor/cache/db_query.py \
        tests/test_cache_db_query.py
git commit -m "feat: r1 db_query helpers (query_field/query_extraction/list_companies)"
```

---

## Task 5: `index` CLI subcommand

**Files:**
- Modify: `src/financial_report_llm_extractor/cli.py`
- Test: `tests/test_cli.py` (extend)

The CLI builds a `priority_map` from the taxonomy file and passes it to `index_run`. It also reads the taxonomy `version` field to use as the default `catalog_version`, with a `--catalog-version` override for callers who know better. If `evaluation.json` itself carries `catalog_version` (forward-compat with R4), the indexer prefers that. A stderr warning is emitted if neither evaluation.json carries the field nor an explicit `--catalog-version` was provided, so historical-run labeling is visible to the operator.

- [ ] **Step 5.1: Write the failing test**

Append to `tests/test_cli.py`:

```python
def test_cli_index_command_scans_runs_dir(
    tmp_path: Path, capsys: "pytest.CaptureFixture[str]"
) -> None:
    """`index` subcommand walks runs dir + writes DB; builds priority_map from
    the taxonomy file; uses taxonomy version as default catalog_version."""
    import json as _json
    from financial_report_llm_extractor.cli import main

    # Reuse the realistic two-file fixture.
    src_eval = (
        Path(__file__).parent / "fixtures" / "cache_sample_run"
        / "evaluation.json"
    )
    src_supp = (
        Path(__file__).parent / "fixtures" / "cache_sample_run"
        / "llm_evidence_supplement.json"
    )
    run_dir = tmp_path / "runs" / "600519_2024-12-31"
    run_dir.mkdir(parents=True)
    (run_dir / "evaluation.json").write_text(
        src_eval.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (run_dir / "llm_evidence_supplement.json").write_text(
        src_supp.read_text(encoding="utf-8"), encoding="utf-8"
    )

    # Tiny taxonomy: version + 3 fields with priorities.
    tax_path = tmp_path / "tax.json"
    tax_path.write_text(_json.dumps({
        "catalog_id": "tiny",
        "version": "test-1",
        "source_priority_catalog": "tiny",
        "fields": {
            "revenue": {"priority": "P0", "domain": "x", "statement_type": "x",
                        "value_type": "money", "source_mode": "direct",
                        "period_type": "x", "scope_expectation": "x",
                        "currency_requirement": "applicable",
                        "unit_requirement": "applicable",
                        "evidence_requirement": "x", "fallback_policy": "x",
                        "description": "x"},
            "audit_opinion": {"priority": "P4", "domain": "x",
                              "statement_type": "x", "value_type": "text",
                              "source_mode": "pdf_only", "period_type": "x",
                              "scope_expectation": "x",
                              "currency_requirement": "not_applicable",
                              "unit_requirement": "not_applicable",
                              "evidence_requirement": "x",
                              "fallback_policy": "x", "description": "x"},
            "fix_assets": {"priority": "P0", "domain": "x",
                           "statement_type": "x", "value_type": "money",
                           "source_mode": "direct", "period_type": "x",
                           "scope_expectation": "x",
                           "currency_requirement": "applicable",
                           "unit_requirement": "applicable",
                           "evidence_requirement": "x",
                           "fallback_policy": "x", "description": "x"},
        },
    }), encoding="utf-8")
    db_path = tmp_path / "out.db"
    exit_code = main([
        "index",
        "--runs", str(tmp_path / "runs"),
        "--db", str(db_path),
        "--taxonomy", str(tax_path),
    ])
    assert exit_code == 0
    assert db_path.exists()

    from financial_report_llm_extractor.cache.db_query import (
        list_companies,
        query_field,
    )
    assert ("600519", "2024-12-31", "CN", "test-1") in list_companies(
        db_path=db_path
    )
    audit_row = query_field(
        db_path=db_path, company="600519",
        period_end="2024-12-31", field_id="audit_opinion",
    )
    assert audit_row is not None
    assert audit_row["priority"] == "P4"
    assert audit_row["value"].startswith("标准无保留意见")


def test_cli_index_command_explicit_catalog_version_overrides_taxonomy(
    tmp_path: Path,
) -> None:
    """`--catalog-version` override beats taxonomy version field."""
    import json as _json
    from financial_report_llm_extractor.cli import main

    src_eval = (Path(__file__).parent / "fixtures" / "cache_sample_run"
                / "evaluation.json")
    run_dir = tmp_path / "runs" / "600519_2024-12-31"
    run_dir.mkdir(parents=True)
    (run_dir / "evaluation.json").write_text(
        src_eval.read_text(encoding="utf-8"), encoding="utf-8"
    )

    tax_path = tmp_path / "tax.json"
    tax_path.write_text(_json.dumps({
        "catalog_id": "x", "version": "should-not-be-used",
        "source_priority_catalog": "x", "fields": {},
    }), encoding="utf-8")
    db_path = tmp_path / "out.db"
    main([
        "index",
        "--runs", str(tmp_path / "runs"),
        "--db", str(db_path),
        "--taxonomy", str(tax_path),
        "--catalog-version", "historical-snapshot",
    ])

    from financial_report_llm_extractor.cache.db_query import list_companies
    assert ("600519", "2024-12-31", "CN", "historical-snapshot") in (
        list_companies(db_path=db_path)
    )
```

- [ ] **Step 5.2: Run test to verify it fails**

```bash
uv run pytest tests/test_cli.py::test_cli_index_command_scans_runs_dir -v
```

Expected: FAIL — `index` subcommand not registered.

- [ ] **Step 5.3: Add `index` subparser**

Modify `src/financial_report_llm_extractor/cli.py`. Find the section where other subparsers are added (search for `subparsers.add_parser(`) and add after the last one (before the existing `evaluate_parser` for `evaluate-company`):

```python
    index_parser = subparsers.add_parser("index")
    index_parser.add_argument("--runs", type=Path, required=True,
                              help="Directory containing per-company run subdirs")
    index_parser.add_argument("--db", type=Path, required=True,
                              help="SQLite DB path to create/update")
    index_parser.add_argument(
        "--taxonomy", type=Path,
        default=Path("field_catalog/turtle_v015_field_taxonomy.json"),
        help="Taxonomy JSON for catalog version + priority denormalization",
    )
    index_parser.add_argument(
        "--catalog-version", type=str, default=None,
        help="Override catalog_version (default: from --taxonomy 'version' field)",
    )
```

In the `main()` dispatch block (search for `if args.command == "ingest":`), add this branch (place it after one of the existing branches; order does not matter):

```python
    if args.command == "index":
        import sys as _sys
        from financial_report_llm_extractor.cache.db import (
            init_db as _init_db,
        )
        from financial_report_llm_extractor.cache.indexer import (
            index_run as _index_run,
        )
        taxonomy = json.loads(args.taxonomy.read_text(encoding="utf-8"))
        taxonomy_version = str(taxonomy.get("version", "unknown"))
        catalog_version = args.catalog_version or taxonomy_version
        priority_map = {
            fid: str(info.get("priority", ""))
            for fid, info in taxonomy.get("fields", {}).items()
        }
        if (
            args.catalog_version is None
            and taxonomy_version != "unknown"
        ):
            print(
                f"warning: using current taxonomy version "
                f"'{taxonomy_version}' as catalog_version for all runs; "
                f"historical runs may have been generated under a different "
                f"catalog. Pass --catalog-version to override.",
                file=_sys.stderr,
            )
        _init_db(args.db)
        count_runs = 0
        count_fields = 0
        for sub in sorted(args.runs.iterdir()):
            if not sub.is_dir() or not (sub / "evaluation.json").exists():
                continue
            count_fields += _index_run(
                run_dir=sub, db_path=args.db,
                catalog_version=catalog_version,
                priority_map=priority_map,
            )
            count_runs += 1
        print(json.dumps({
            "indexed_runs": count_runs,
            "indexed_fields": count_fields,
            "db": str(args.db),
            "catalog_version": catalog_version,
        }, indent=2, sort_keys=True))
        return 0
```

(`json` and `Path` are already imported at the top of `cli.py`; `sys` is imported lazily inside the branch to avoid affecting unrelated commands.)

- [ ] **Step 5.4: Run tests to verify they pass**

```bash
uv run pytest tests/test_cli.py::test_cli_index_command_scans_runs_dir \
              tests/test_cli.py::test_cli_index_command_explicit_catalog_version_overrides_taxonomy \
              -v
```

Expected: 2 passed.

- [ ] **Step 5.5: Run full suite + ruff + mypy**

```bash
uv run pytest -q
uv run ruff check .
uv run mypy src tests
```

Expected: all green; no regression.

- [ ] **Step 5.6: Commit**

```bash
git add src/financial_report_llm_extractor/cli.py tests/test_cli.py
git commit -m "feat: r1 cli index command — scan runs into db with priority_map"
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
    tmp_path: Path, capsys: "pytest.CaptureFixture[str]"
) -> None:
    """`query --field` outputs single field row as JSON."""
    import json as _json
    from financial_report_llm_extractor.cli import main

    src_eval = (Path(__file__).parent / "fixtures" / "cache_sample_run"
                / "evaluation.json")
    src_supp = (Path(__file__).parent / "fixtures" / "cache_sample_run"
                / "llm_evidence_supplement.json")
    run_dir = tmp_path / "runs" / "600519_2024-12-31"
    run_dir.mkdir(parents=True)
    (run_dir / "evaluation.json").write_text(
        src_eval.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (run_dir / "llm_evidence_supplement.json").write_text(
        src_supp.read_text(encoding="utf-8"), encoding="utf-8"
    )
    tax_path = tmp_path / "tax.json"
    tax_path.write_text(_json.dumps({
        "catalog_id": "x", "version": "v1",
        "source_priority_catalog": "x",
        "fields": {"audit_opinion": {
            "priority": "P4", "domain": "x", "statement_type": "x",
            "value_type": "text", "source_mode": "pdf_only",
            "period_type": "x", "scope_expectation": "x",
            "currency_requirement": "not_applicable",
            "unit_requirement": "not_applicable",
            "evidence_requirement": "x", "fallback_policy": "x",
            "description": "x"}},
    }), encoding="utf-8")
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
        "--field", "audit_opinion",
    ])
    assert exit_code == 0
    body = _json.loads(capsys.readouterr().out)
    assert body["field_id"] == "audit_opinion"
    assert body["value"].startswith("标准无保留意见")
    assert body["evidence_page"] == 55
    assert body["priority"] == "P4"


def test_cli_query_command_without_field_returns_full_extraction(
    tmp_path: Path, capsys: "pytest.CaptureFixture[str]"
) -> None:
    import json as _json
    from financial_report_llm_extractor.cli import main

    src_eval = (Path(__file__).parent / "fixtures" / "cache_sample_run"
                / "evaluation.json")
    src_supp = (Path(__file__).parent / "fixtures" / "cache_sample_run"
                / "llm_evidence_supplement.json")
    run_dir = tmp_path / "runs" / "600519_2024-12-31"
    run_dir.mkdir(parents=True)
    (run_dir / "evaluation.json").write_text(
        src_eval.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (run_dir / "llm_evidence_supplement.json").write_text(
        src_supp.read_text(encoding="utf-8"), encoding="utf-8"
    )
    tax_path = tmp_path / "tax.json"
    tax_path.write_text(_json.dumps({
        "catalog_id": "x", "version": "v1",
        "source_priority_catalog": "x", "fields": {},
    }), encoding="utf-8")
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
    assert set(body["fields"]) == {"revenue", "audit_opinion", "fix_assets"}


def test_cli_query_command_miss_returns_exit_1(
    tmp_path: Path, capsys: "pytest.CaptureFixture[str]"
) -> None:
    from financial_report_llm_extractor.cli import main
    from financial_report_llm_extractor.cache.db import init_db

    db_path = tmp_path / "out.db"
    init_db(db_path)
    exit_code = main([
        "query", "--db", str(db_path),
        "--company", "nope", "--period", "2024-12-31", "--field", "x",
    ])
    assert exit_code == 1
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
              tests/test_cli.py::test_cli_query_command_miss_returns_exit_1 \
              -v
```

Expected: 3 passed.

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

In `CLAUDE.md`, find the "分阶段模块" table (search for `| 阶段 | 模块 | 职责 |`). Add a new row after the most recent phase row:

```markdown
| R1 | `cache/db_schema.py` + `db.py` + `indexer.py` + `db_query.py` | Two-level extraction cache layer-1: SQLite DB at `data/extracted.db` indexed from `tmp/runs/*/{evaluation,llm_evidence_supplement}.json` joined by field_id. New CLI `index` + `query` commands. Zero pipeline behavior change. Schema: `extractions` (company, period_end, market, catalog_version PK) + `field_values` (company, period_end, field_id PK; priority + reason + bucket + JSON-encoded value + LLM page/confidence/reasoning). See `docs/superpowers/plans/2026-05-13-extraction-cache-db-overview.md`. |
```

- [ ] **Step 7.2: Add §6 entry to phase-summary**

In `docs/2026-05-11-phase-summary.md`, find the §6 unresolved-items table. Add a new row:

```markdown
| **R1 SQLite indexer (`data/extracted.db`)** | **已落地 (2026-05-13)** | R1 plan | New `cache/` module + `index` / `query` CLI commands. Indexes existing `tmp/runs/*/{evaluation,llm_evidence_supplement}.json` joined by field_id. `field_values` is latest-catalog-version only; `extractions` keeps history. R2 (provider fetch cache) + R3 (LLM cache) + R4 (DB-aware `pipeline` command) follow in separate PRs. |
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

- [ ] `uv run pytest -q` shows 12+ new tests passing (3 schema + 5 db + 9 indexer + 5 query + 5 CLI = 27 new), no regressions in existing 630+ tests
- [ ] `uv run ruff check .` clean
- [ ] `uv run mypy src tests` clean
- [ ] `uv run financial-report-llm-extractor index --runs tmp/runs --db data/extracted.db` produces a non-empty DB with both `extractions` and `field_values` rows; LLM-bucket rows have value/page/confidence from `llm_evidence_supplement.json`
- [ ] `uv run financial-report-llm-extractor query --db data/extracted.db --company 600519 --period 2024-12-31 --field audit_opinion` returns JSON containing the actual LLM-extracted opinion text and page reference
- [ ] No new files outside `src/financial_report_llm_extractor/cache/`, `tests/test_cache_*.py`, `tests/fixtures/cache_sample_run/`, `docs/superpowers/plans/`, plus surgical edits to `cli.py`, `CLAUDE.md`, `docs/2026-05-11-phase-summary.md`, `tests/test_cli.py`
- [ ] No new entries in `pyproject.toml` `dependencies` (stdlib only)
- [ ] CLAUDE.md "分阶段模块" table references R1
- [ ] Phase-summary §6 lists R1 as complete with date

## Self-Review

- [x] **Two-file data source**: Task 3 reads BOTH `evaluation.json` and `llm_evidence_supplement.json`. Fixture supplies both. Tests explicitly assert that `clean_present` value comes from evaluation, `llm_supplement_present` value comes from supplement.
- [x] **Test-dir convention**: all test files are flat `tests/test_cache_*.py` matching project pattern. Fixtures under `tests/fixtures/cache_sample_run/` matching the existing `tests/fixtures/` convention.
- [x] **catalog_version handling**: indexer prefers `evaluation.json.catalog_version` if present (forward-compat with R4), falls back to CLI argument; CLI defaults to taxonomy `version` field but emits a stderr warning so historical-run mislabeling is visible. `--catalog-version` flag overrides.
- [x] **field_values latest-only semantic**: Task 3 docstring + Task 7 phase-summary entry call this out explicitly. Test `test_index_run_different_catalog_versions_extractions_coexist` locks the semantic.
- [x] **`reason` column**: added to `field_values` schema, populated from `evaluation.json.fields[fid].reason`, asserted by `test_index_run_unresolved_conflict_has_reason`.
- [x] **`priority` denormalized**: added to `field_values` schema with `idx_field_values_priority` index; populated by CLI from taxonomy `priority` field; asserted by all clean/llm test rows.
- [x] **Value JSON-encoding**: documented in `db_schema.py` docstring and Task 3 implementation; tests use `json.loads(row[1])` to decode.
- [x] **Type consistency**: `init_db(db_path)`, `connect(db_path)`, `index_run(*, run_dir, db_path, catalog_version, priority_map)`, `query_field(*, db_path, company, period_end, field_id)` — same names + signatures across tasks. CLI dispatch references same.
- [x] **No placeholders**: every step has executable code or exact bash command. No "TBD" / "add validation".
