# Provider Field Candidate Discovery Spec

> Date: 2026-05-03
> Status: design spec
> Scope: use the checked-in provider baseline fixture to discover candidate AKShare/Yahoo raw fields for Turtle P0/P1 mapping expansion.

## 1. Purpose

The provider field baseline is now replayable from local fixtures. The next step should use that data to expand source mappings without repeatedly calling AKShare or Yahoo/yfinance.

This phase creates a deterministic candidate discovery report. It compares Turtle taxonomy fields against observed provider raw field names and codes, then outputs reviewable candidates. It does not automatically promote candidates into the production source mapping catalog.

## 2. Goals

This phase must provide:

- Offline candidate discovery from `tests/fixtures/provider_captures/provider_field_baseline/`.
- Support for compressed `source_inventory.jsonl.gz`.
- Candidate generation for Turtle P0/P1 fields.
- Candidate ranking based on deterministic signals.
- Separate AKShare and Yahoo candidate groups.
- A JSON report suitable for later catalog-editing work.
- A compact Markdown review report for human inspection.
- Tests that use local fixtures or small in-memory samples only.

## 3. Non-Goals

This phase does not:

- Call AKShare, Yahoo, yfinance, or any network source.
- Modify `field_catalog/turtle_v015_source_mapping_minimal.json`.
- Make LLM mapping decisions.
- Validate final Turtle coverage.
- Resolve cross-source value conflicts.
- Add PDF evidence or LLM fallback.
- Expand P2/P3/P4 fields.

## 4. Inputs

Required inputs:

- `field_catalog/turtle_v015_field_taxonomy.json`
- `field_catalog/turtle_v015_source_mapping_minimal.json`
- `tests/fixtures/provider_captures/provider_field_baseline/provider_field_inventory_summary.json`
- `tests/fixtures/provider_captures/provider_field_baseline/source_inventory.jsonl.gz`

The summary gives the observed field surface. The inventory gives period-level support and evidence references. The source mapping catalog provides existing aliases so the report can distinguish already-covered aliases from new candidates.

## 5. Candidate Scope

Default discovery scope:

- Priorities: `P0,P1`
- Statement types: derived from taxonomy per field.
- Providers: `akshare,yahoo`
- Markets/tickers: all fixture targets.
- Periods: fixture periods only, already bounded to latest annual periods.

Fields with taxonomy source modes `pdf_only` or `llm_review` should appear in the report as not applicable for source candidate discovery. They should not generate source-direct candidates.

## 6. Matching Signals

Candidate ranking should be deterministic and explainable.

Signals:

- `existing_alias`: provider raw field exactly matches an alias already present in the source mapping catalog.
- `exact_text`: normalized Turtle field tokens match normalized raw field name/code.
- `keyword_overlap`: meaningful tokens overlap between Turtle metadata and raw field name/code.
- `statement_match`: raw field appears under the taxonomy statement type.
- `provider_presence`: raw field appears for one or more target companies.
- `period_support`: raw field has present records across multiple annual periods.
- `cross_provider_support`: similar candidates exist in both AKShare and Yahoo.

Normalization rules:

- Case-insensitive comparison for English.
- Ignore punctuation, underscores, repeated whitespace, and common filler words.
- Preserve Chinese field names as text tokens.
- Treat raw field code and raw field name as separate candidate labels.
- Do not translate Chinese to English in this deterministic phase.

The report should include weak keyword candidates, but it must label them as `weak`. Only existing aliases and exact text matches may be `strong`.

## 7. Output Contract

Primary artifact:

```text
provider_field_candidate_report.json
```

Recommended schema:

```json
{
  "report_id": "provider_field_candidate_report",
  "version": "1",
  "taxonomy_catalog": "turtle_v015_field_taxonomy",
  "mapping_catalog": "turtle_v015_source_mapping_minimal",
  "fixture": "provider_field_baseline",
  "priorities": ["P0", "P1"],
  "fields": {
    "revenue": {
      "priority": "P0",
      "statement_type": "income_statement",
      "source_mode": "direct",
      "status": "has_candidates",
      "providers": {
        "akshare": {
          "candidates": [
            {
              "raw_field_name": "营业收入",
              "raw_field_code": "OPERATE_INCOME",
              "score": 100,
              "strength": "strong",
              "signals": ["existing_alias", "statement_match", "period_support"],
              "target_count": 1,
              "period_count": 5,
              "record_count": 5
            }
          ]
        }
      }
    }
  },
  "summary": {
    "field_count": 33,
    "fields_with_candidates": 0,
    "fields_without_candidates": 0,
    "not_applicable_fields": 0
  }
}
```

Markdown artifact:

```text
provider_field_candidate_report.md
```

The Markdown report should group by priority and field id, showing the top candidates per provider and why they were selected.

## 8. Statuses

Field-level statuses:

- `has_candidates`: at least one candidate was found.
- `no_candidates`: source-direct field but no provider candidate was found.
- `not_applicable`: taxonomy source mode is not source-direct for this phase.
- `catalog_gap`: field is in taxonomy but missing from the selected mapping catalog and requires mapping work.

Candidate strengths:

- `strong`: exact existing alias or exact normalized match.
- `medium`: strong keyword overlap plus statement match.
- `weak`: limited token overlap; requires review.

## 9. CLI And Artifacts

Add a CLI entrypoint only if it fits existing CLI patterns without broad refactoring. Recommended command:

```bash
financial-report-llm-extractor discover-provider-fields \
  --taxonomy field_catalog/turtle_v015_field_taxonomy.json \
  --mapping-catalog field_catalog/turtle_v015_source_mapping_minimal.json \
  --inventory tests/fixtures/provider_captures/provider_field_baseline/source_inventory.jsonl.gz \
  --summary tests/fixtures/provider_captures/provider_field_baseline/provider_field_inventory_summary.json \
  --out tmp/runs/provider_field_candidate_discovery
```

If the existing CLI surface is too crowded for this phase, a module-level writer function with tests is sufficient. The implementation plan should decide after checking current CLI patterns.

## 10. Testing Contract

Tests must cover:

- Loading compressed baseline inventory.
- Building provider raw field indexes by source, ticker, statement type, raw field name, and raw field code.
- Existing source aliases become strong candidates.
- Statement mismatches lower or block candidate strength.
- Fields with `pdf_only` or `llm_review` source modes are not applicable.
- The checked-in provider baseline fixture can produce a stable candidate report summary.
- Markdown report contains field id, provider, raw field name/code, strength, and signals.

Tests must not use network access.

## 11. Success Criteria

This phase is complete when:

- Candidate report generation works from the checked-in compressed baseline fixture.
- P0/P1 Turtle fields receive deterministic provider candidates or explicit no-candidate/not-applicable statuses.
- Existing minimal mapping aliases are recognized as strong candidates.
- The report is stable enough to drive the next source mapping catalog expansion phase.
- All verification runs pass without API calls.
