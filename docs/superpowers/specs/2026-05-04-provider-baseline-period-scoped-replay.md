# Provider Baseline Period-Scoped Replay Spec

> Date: 2026-05-04
> Status: design spec
> Scope: replay the checked-in provider baseline fixture through source mapping, reconciliation, and review export without provider calls, while selecting one annual period per company/source slice.

## 1. Purpose

The expanded source mapping catalog now has 15 P0/P1 fields. Replaying the small captured fixtures still works, but it does not prove the new six promoted mappings are useful because those fixtures contain only narrow statement families.

The broader provider baseline fixture has 6,771 source inventory records across 5 annual periods, 3 companies, 2 providers, and 3 statement families. Directly sending the whole fixture into `map_source_inventory()` produces `0/15` coverage because every mapped field has multiple periods and is reconciled as `candidate periods differ`.

This phase makes that fixture usable by selecting the latest annual period per company/source, then replaying those period-scoped records through the existing deterministic source-first pipeline.

## 2. Goals

This phase must provide:

- A no-network replay path for `tests/fixtures/provider_captures/provider_field_baseline/source_inventory.jsonl.gz`.
- Deterministic grouping by provider capture target company id.
- Latest annual period selection per `(source, market, provider_ticker)` group.
- Per-company coverage for:
  - AKShare only,
  - Yahoo only,
  - combined AKShare + Yahoo.
- Per-slice artifacts:
  - `source_inventory.jsonl`,
  - `turtle_mapping.json`,
  - `source_coverage_summary.json`,
  - `reconciliation_report.json`,
  - `extraction_result.json`,
  - `review_summary.json`.
- A top-level JSON/Markdown summary that makes present fields, missing fields, blocked fields, ambiguous fields, conflict fields, and coverage ratios reviewable.
- A CLI or script entrypoint that defaults to checked-in fixtures and writes under `tmp/runs/provider_baseline_period_replay/`.

## 3. Non-Goals

This phase does not:

- Call AKShare, Yahoo, yfinance, PDF parsing, or LLM providers.
- Change the source mapping catalog.
- Automatically promote medium or weak candidates.
- Resolve cross-source conflicts.
- Select 5-year time series output.
- Perform FX conversion or unit conversion between `yuan`, `HKD`, and Yahoo `raw`.
- Replace `run_captured_source_validation()` for small single-period fixtures.

## 4. Inputs

Required local inputs:

- `tests/fixtures/provider_captures/provider_field_baseline/source_inventory.jsonl.gz`
- `tests/fixtures/provider_captures/provider_field_baseline/provider_field_inventory_summary.json`
- `field_catalog/turtle_v015_source_mapping_minimal.json`
- `src/financial_report_llm_extractor/structured_sources/capture_targets.py`

The company id mapping must come from `DEFAULT_PROVIDER_FIELD_CAPTURE_TARGETS`, not from ad hoc ticker string rules:

| company_id | akshare provider_ticker | yahoo provider_ticker |
| --- | --- | --- |
| `600519` | `600519` | `600519.SS` |
| `00001` | `00001` | `0001.HK` |
| `01113` | `01113` | `1113.HK` |

## 5. Period Selection

For each provider target group `(provider, market, provider_ticker)`:

- Consider only `source_status == "present"` records with a non-empty `period`.
- Annual periods are records whose date part ends with `-12-31`.
- Select the lexicographically latest annual period in that group.
- Keep all present records for that selected period across statement families.
- Keep non-present records for that group only when there is no selected present period.

This selection is intentionally group-local. It must not select one global period for all providers because provider date string formats can differ (`2025-12-31 00:00:00` vs `2025-12-31`).

## 6. Replay Semantics

For each company id:

- `akshare_only` uses the latest annual records for the AKShare target.
- `yahoo_only` uses the latest annual records for the Yahoo target.
- `combined` uses the union of the two latest annual source slices.

Each slice should run the existing pipeline:

```text
source inventory records
-> map_source_inventory()
-> reconcile_mapped_fields()
-> build_source_first_export(profile="source_only")
-> write_turtle_mapping_artifacts()
-> write_reconciliation_report()
-> write_source_first_export_artifacts()
```

The combined slice must not hide conflicts. If AKShare and Yahoo disagree on period, currency, unit, scope, or value, the output should keep that field in `conflict` or `ambiguous` according to existing reconciliation/export rules.

## 7. Output Layout

Default output directory:

```text
tmp/runs/provider_baseline_period_replay/
  provider_baseline_period_replay_summary.json
  provider_baseline_period_replay_summary.md
  600519/
    akshare_only/
    yahoo_only/
    combined/
  00001/
    akshare_only/
    yahoo_only/
    combined/
  01113/
    akshare_only/
    yahoo_only/
    combined/
```

Each slice directory must contain the standard source-first artifacts listed in section 2.

The top-level JSON summary must include:

- `report_id`
- `catalog_id`
- `catalog_version`
- `inventory_path`
- `summary_path`
- `company_count`
- `companies`
- per company:
  - selected source periods,
  - record counts by slice,
  - coverage by slice,
  - present/missing/ambiguous/blocked/conflict fields by slice,
  - artifact paths.

Generated `tmp/` artifacts are not committed.

## 8. Testing Contract

Tests must cover:

- Latest annual period selection ignores interim periods.
- Selection is per source/ticker group, not global.
- Company ids are resolved through provider capture targets.
- Replay on a synthetic fixture avoids period conflict by selecting one period per source.
- The checked-in provider baseline can be replayed without network calls.
- Top-level summary reports three companies and the expanded catalog denominator of 15 fields.
- Default tests do not call AKShare, Yahoo, yfinance, PDF tooling, or LLM providers.

## 9. Success Criteria

This phase is complete when:

- Provider baseline period-scoped replay runs from checked-in fixture only.
- The full baseline no longer produces `0/15` solely because multiple annual periods were sent into one mapping run.
- The replay summary identifies which of the 15 fields are covered for `600519`, `00001`, and `01113`.
- Remaining gaps are categorized as source availability, mapping ambiguity/blocker, reconciliation conflict, or later PDF/LLM supplement candidates.
- Full verification passes:

```bash
uv run pytest -v
uv run ruff check .
uv run mypy src tests
git diff --check
```
