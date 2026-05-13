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
