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
- `field_values` does NOT declare a SQL FOREIGN KEY to `extractions`. The
  relationship is logical: every field_values row corresponds to the
  "latest" extractions row for the same (company, period_end). Indexer
  enforces this by DELETE-then-INSERT on every re-index. Cross-table
  integrity is application-level, not DB-level.
- R5 schema v2 (2026-05-14): `field_values` PK includes `market` column
  (was 3-column `(company, period_end, field_id)`; now 4-column
  `(company, period_end, market, field_id)`). This allows same (company,
  period_end) under different markets to coexist without DELETE+INSERT
  collision. `init_db()` detects v1 schema via `PRAGMA table_info` and
  rebuilds tables (drop + recreate). `tmp/runs/*` artifacts remain the
  source of truth; operator re-runs `index --rebuild` to repopulate.
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
  market              TEXT NOT NULL,
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
  normalized_value    TEXT,
  canonical_unit      TEXT,
  PRIMARY KEY (company, period_end, market, field_id)
);
""".strip()

CREATE_FIELD_VALUES_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_field_values_field
  ON field_values(field_id);
CREATE INDEX IF NOT EXISTS idx_field_values_bucket
  ON field_values(bucket);
CREATE INDEX IF NOT EXISTS idx_field_values_priority
  ON field_values(priority);
CREATE INDEX IF NOT EXISTS idx_field_values_market
  ON field_values(market);
""".strip()
