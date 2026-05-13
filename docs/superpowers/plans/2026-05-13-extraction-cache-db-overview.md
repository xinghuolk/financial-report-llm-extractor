# Extraction Cache & SQLite DB — Overview Plan

> Date: 2026-05-13
> Branch: `feature/extraction-cache-db`
> Status: planning. R1 detailed plan in companion doc `2026-05-13-r1-sqlite-indexer.md`.

## Goal

Add a two-level persistence architecture to the extractor:

- **Layer 1 (final, queryable)**: SQLite DB at `data/extracted.db` storing canonical extraction results, queryable across companies / periods / fields without re-running the pipeline.
- **Layer 2 (intermediate cache)**: `tmp/.cache/` for provider raw responses and LLM call results, eliminates redundant network and LLM calls across CLI invocations.

Together they let downstream agents and re-runs share work: ask "give me 600519/2024 revenue" → DB hit, zero cost. Trigger a fresh pipeline → tmp/.cache deduplicates provider + LLM work.

## Architecture Invariants

1. **DB is a derived view; `tmp/runs/` is source of truth.** Deleting the DB must allow full reconstruction via `index --rebuild`. The reverse is not supported — DB rows alone do not encode enough provenance.
2. **`catalog_version` is part of every cache key.** Catalog changes (G1/G2/G3/G4-C style) auto-invalidate. The system never silently returns rows generated under an older field set.
3. **LLM cache is keyed by `(chunk_hash, prompt_template_version, model)`.** Deterministic given fixed catalog + same model = permanent cache hit. Catalog or model change = automatic miss.
4. **Zero new Python dependencies.** `sqlite3` is stdlib; hashing via `hashlib`; everything else is already in use. Preserves the project's "stdlib-only runtime" constraint codified in CLAUDE.md.
5. **Source-first deterministic logic unchanged.** Caching is purely transport-layer / artifact-layer; reconciliation, source policy, and Turtle mapping continue to operate on the same inputs they always have.
6. **Cache is opt-in for tooling, mandatory for `pipeline` command.** Existing `fetch-source-inventory` and `evaluate-company` keep their current behavior unless `--skip-if-cached` is passed. A new `pipeline` command is DB-aware by default.

## Storage Layout

```
data/
└── extracted.db                          # Layer 1: queryable canonical results

tmp/
├── runs/<cid>_<period>/                  # raw provenance per-run (current behavior)
│   ├── source_inventory.jsonl
│   ├── llm_evidence_supplement.json
│   ├── evaluation.json                   # ← indexed into Layer 1
│   └── ... (full audit trail)
└── .cache/                               # Layer 2: cross-run dedup
    ├── akshare/<cid>_<period>.json       # + meta.mtime for TTL
    ├── yahoo/<cid>_<period>.json         # + meta.mtime for TTL
    └── llm/<chunk_hash>_<prompt_hash>_<model>.json
```

## SQLite Schema

```sql
CREATE TABLE extractions (
  company         TEXT NOT NULL,
  period_end      TEXT NOT NULL,        -- e.g., '2024-12-31'
  market          TEXT NOT NULL,        -- CN / HK
  report_type     TEXT NOT NULL,        -- annual / semi_annual / quarterly
  catalog_version TEXT NOT NULL,        -- from taxonomy catalog version field
  schema_version  TEXT NOT NULL,        -- evaluation.json schema_version
  generated_at    TEXT NOT NULL,        -- ISO 8601
  artifact_path   TEXT NOT NULL,        -- relative path to tmp/runs/<cid>_<period>/
  llm_provider    TEXT,                 -- deepseek / openai-codex / null
  llm_model       TEXT,
  PRIMARY KEY (company, period_end, market, catalog_version)
);

CREATE TABLE field_values (
  company             TEXT NOT NULL,
  period_end          TEXT NOT NULL,
  field_id            TEXT NOT NULL,
  bucket              TEXT NOT NULL,
  value               TEXT,             -- JSON-encoded scalar (string or number)
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

CREATE INDEX idx_field_values_field ON field_values(field_id);
CREATE INDEX idx_field_values_bucket ON field_values(bucket);
```

`value` stored as JSON string so it can hold both numeric values (`"42000000"`) and text values (`"\"unqualified opinion ...\""`). Caller decodes via `json.loads`.

## Stages

Four independent stages, each shipped as its own PR:

| Stage | Name | Effort | Independence | Builds on |
|---|---|---|---|---|
| **R1** | SQLite indexer (DB write + query) | ~half day | ✓ Fully independent. Reads existing JSON artifacts. | nothing |
| **R2** | Provider fetch cache (`tmp/.cache/akshare`, `tmp/.cache/yahoo`) + TTL + `--skip-if-cached` | ~half day | ✓ Fully independent. Only modifies `fetch-source-inventory`. | nothing |
| **R3** | LLM call cache (`tmp/.cache/llm/<hash>.json`) | ~half day | ✓ Fully independent. Modifies LLM transport layer. | nothing |
| **R4** | `pipeline` one-stop CLI command, DB-aware, auto-indexes | ~1 day | Depends on R1 (DB) + R2 (fetch cache) + R3 (LLM cache) | R1, R2, R3 |

**Total**: ~3 days, 4 stages, 4 PRs.

### R1: SQLite Indexer

**Detailed plan**: `docs/superpowers/plans/2026-05-13-r1-sqlite-indexer.md`

New module `src/financial_report_llm_extractor/cache/` with:
- `db_schema.py` — DDL constants
- `db.py` — `init_db()` + connection helpers
- `indexer.py` — `index_run(run_dir, db_path)` reads evaluation.json + inserts rows
- `db_query.py` — `query(db_path, company, period, field_id)` + bulk queries

New CLI commands:
- `index --runs <dir> --db <path>` — scan `tmp/runs/*` and write DB
- `query --db <path> --company <id> [--period <date>] [--field <id>]` — output JSON to stdout

No changes to pipeline behavior. Downstream agents start using the DB without any other code change required.

### R2: Provider Fetch Cache

Files modified:
- `src/financial_report_llm_extractor/structured_sources/source_inventory_fetch.py` — wrap `_fetch_akshare_for_company` and `_fetch_yahoo_for_company` with cache layer
- `src/financial_report_llm_extractor/cache/` — new `provider_cache.py` with `read_or_fetch(key, fetch_callable, ttl)`

New CLI flags on `fetch-source-inventory`:
- `--skip-if-cached` — return successfully without network call if cache hit + fresh
- `--cache-ttl-hours <n>` — default 24; `0` = always fresh / always re-fetch
- `--no-cache` — bypass cache entirely

Cache file format: `{"fetched_at": "iso8601", "records": [...]}`. TTL compared against `fetched_at`.

Cache miss / expired = re-fetch and overwrite. Cache invalidation: `rm -rf tmp/.cache/`.

### R3: LLM Call Cache

Files modified:
- `src/financial_report_llm_extractor/llm_transport.py` — wrap `complete_json` with cache layer at the `OpenAiCompatibleClient` / `CodexResponsesClient` / `ClaudeCodeMessagesClient` boundary
- `src/financial_report_llm_extractor/cache/llm_cache.py` — new

Cache key: SHA-256 of `(chunk_hash, system_prompt, user_payload, model)`. Stored as `tmp/.cache/llm/<sha256>.json`.

Catalog change → chunks differ → hash differs → automatic miss. Model change → hash differs → automatic miss. No TTL (deterministic given inputs).

New CLI flag on `extract-llm` / `evaluate-company`:
- `--no-llm-cache` — bypass

Cache hit during a run is logged in the per-run `extraction_result.json` so the audit trail records which fields were served from cache vs fresh LLM call.

### R4: Pipeline DB-Aware Command

New CLI command `pipeline`:

```bash
financial-report-llm-extractor pipeline \
  --company 600519 --year 2024 --market CN \
  --pdf downloads/cn_stocks/600519/annual/2024_年度报告.pdf \
  --llm-config tmp/llm_configs/codex_subscription.json \
  --db data/extracted.db
```

Flow:
1. **Pre-check**: query DB for `(company, period_end, market, catalog_version=current)`. If hit + `--force` not set, return JSON pointing to cached `artifact_path`. Exit 0.
2. **Fetch**: invoke `fetch-source-inventory` (uses R2 cache).
3. **Evaluate**: invoke `evaluate-company` (uses R3 cache via the LLM transport layer).
4. **Index**: insert/update DB row from new `evaluation.json`.

Existing commands continue to work without DB; `pipeline` is the new orchestrator.

`evaluate-company` gets an optional `--db <path>` argument: when set, post-run insert/update DB. Without it, behaves exactly as today.

## Open Decisions Locked In

- **`value` column is TEXT (JSON-encoded)**, not separate `value_number` / `value_text`. Reason: extraction values mix money / text / decimal types per `FieldValueType` enum; JSON unifies storage without a polymorphic schema.
- **Cache TTL defaults to 24 hours for providers, no TTL for LLM.** Provider data updates over time (annual report restatements happen); LLM responses are deterministic given fixed inputs.
- **Catalog version is read from `field_catalog/turtle_v015_field_taxonomy.json` `version` field at run time.** Not hardcoded in the cache module.
- **No web UI, no daemon, no migration tooling.** SQLite file is small and ephemeral; if schema evolves, drop the DB and `index --rebuild`.

## Risk Register

| Risk | Mitigation |
|---|---|
| DB schema drift between code and existing artifacts | `index --rebuild` always rebuilds from JSON; JSON is authoritative |
| LLM cache key collision (different content, same hash) | SHA-256 collision probability is negligible at our scale (<10^6 entries); if it ever matters, switch to keyed-by-content-hash |
| Cache poisoning (bad data written to cache) | Cache files are per-(cid, period) atomic writes; bad data affects one entry, never silently spreads; `--no-cache` always works |
| `tmp/.cache/` growth unbounded | Document `rm -rf tmp/.cache/llm` is safe; later add `cache-stats` / `cache-prune` if needed (not in scope here) |
| DB grows unbounded | At ~70 fields × 100 companies × 5 years = 35K rows. Negligible for SQLite |
| Concurrent writes (two `pipeline` runs at once) | Use `sqlite3.connect(timeout=10)` + `BEGIN IMMEDIATE`; conflicts retry. Document not safe for true concurrency at scale. |

## Out of Scope for This Phase

- **Cross-version diff queries** ("how did revenue change between 2023 and 2024 data") — possible with DB but not implemented; downstream Turtle Agent already does this.
- **Web UI / dashboard** — CLI only.
- **Distributed cache** — single-host SQLite + filesystem cache.
- **Auto-eviction policies** — manual `rm -rf` for now.
- **Cache statistics command** — defer until usage demands.
- **Backwards-compatibility migrations** — drop + rebuild.

## Self-Review Checklist

- [x] All 4 stages independent or with explicit dependency (R4 depends on R1+R2+R3)
- [x] Each stage produces a working, testable PR on its own
- [x] DB schema decisions documented (TEXT value, JSON-encoded, why)
- [x] Cache invariants explicit (catalog_version in key, no silent stale rows)
- [x] Zero new dependencies confirmed (sqlite3 + hashlib are stdlib)
- [x] Out-of-scope items listed so reviewers don't ask why X is missing

## Next Step

Start R1 per `docs/superpowers/plans/2026-05-13-r1-sqlite-indexer.md`.
