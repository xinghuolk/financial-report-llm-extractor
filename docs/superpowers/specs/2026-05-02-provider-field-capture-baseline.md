# Provider Field Capture Baseline Spec

> Date: 2026-05-02
> Status: design spec
> Scope: capture AKShare and Yahoo/yfinance raw statement fields once for the validation companies, then drive mapping work from replayable fixtures.

## 1. Purpose

The source-first roadmap should not repeatedly call AKShare or Yahoo/yfinance while mapping Turtle fields. Provider calls are useful to discover real raw field shapes, but iterative development should replay saved artifacts.

This stage creates a provider field capture baseline after PC2 artifact manifest/replay support. It captures target companies and statement families once, saves raw provider artifacts and source inventory, and writes a field inventory summary that can be used to expand Turtle source mappings without another API request.

## 2. Goals

This stage must provide:

- A deterministic target matrix for provider field capture.
- One opt-in real-provider capture path for AKShare and Yahoo/yfinance.
- Raw artifact persistence through `SourceArtifactStore`.
- `source_artifact_manifest.json` validation through PC2.
- `source_inventory.jsonl` for replay.
- `provider_field_inventory_summary.json` listing observed raw field names, raw field codes, periods, currencies, units, statuses, and artifact counts.
- A fixture workflow that promotes successful captures into `tests/fixtures/provider_captures/<capture_id>/`.
- No default network calls in tests.

## 3. Non-Goals

This stage does not:

- Add new Turtle field mappings.
- Decide final source coverage.
- Reconcile AKShare and Yahoo values.
- Add PDF or LLM fallback.
- Capture every market, every listed company, or every provider endpoint.
- Retry provider calls aggressively.

Provider failures remain structured source errors. A failed Yahoo ticker or missing AKShare statement should be visible in the summary instead of blocking unrelated captured statements.

## 4. Capture Scope

The capture baseline covers the current validation companies and the three core statements:

| Company id | Provider | Provider ticker | Market | Statements | Currency | Unit |
| --- | --- | --- | --- | --- | --- | --- |
| `600519` | AKShare | `600519` with exchange `SH` | `CN` | `balance_sheet`, `income_statement`, `cash_flow` | `CNY` | `yuan` |
| `00001` | AKShare | `00001` | `HK` | `balance_sheet`, `income_statement`, `cash_flow` | `HKD` | `HKD` |
| `01113` | AKShare | `01113` | `HK` | `balance_sheet`, `income_statement`, `cash_flow` | `HKD` | `HKD` |
| `600519` | Yahoo/yfinance | `600519.SS` | `CN` | `balance_sheet`, `income_statement`, `cash_flow` | `CNY` | `raw` |
| `00001` | Yahoo/yfinance | `0001.HK` | `HK` | `balance_sheet`, `income_statement`, `cash_flow` | `HKD` | `raw` |
| `01113` | Yahoo/yfinance | `1113.HK` | `HK` | `balance_sheet`, `income_statement`, `cash_flow` | `HKD` | `raw` |

The company id is the stable validation id. The provider ticker is the actual input to the provider adapter.

The baseline is not a full historical archive. For each provider/company/statement target, inventory rows should keep the latest five annual reporting periods by default. Within those five annual periods, the capture must preserve every provider-returned raw field, including fields that are not mapped to Turtle yet. If a provider does not expose annual period strings, the fallback is the latest five available periods. Source error, missing, and unsupported records should remain visible even when they have no period.

## 5. Artifact Contract

Each successful capture run should write:

```text
source_artifacts/
  akshare/
    <artifact_id>.json
  yahoo/
    <artifact_id>.json
source_artifact_manifest.json
source_inventory.jsonl
provider_field_inventory_summary.json
real_source_validation_summary.json
turtle_mapping.json
reconciliation_report.json
extraction_result.json
review_summary.json
```

The first four files are the baseline for future mapping work. The mapping/reconciliation/export artifacts are still useful smoke checks, but this stage is not judged by Turtle coverage.

## 6. Field Inventory Summary Contract

`provider_field_inventory_summary.json` should be a compact index over `source_inventory.jsonl`, not a replacement for raw artifacts.

It should include:

- `sample_set`: `provider_field_baseline` for real capture runs, or the validation mode for smaller tests.
- `record_count`.
- `source_artifact_count` when a manifest exists.
- `status_counts` across inventory rows.
- `targets`, grouped by `source`, `market`, `ticker`, and `statement_type`.
- For each target:
  - `record_count`
  - `status_counts`
  - sorted `raw_field_names`
  - sorted `raw_field_codes`
  - sorted `periods`
  - sorted `currencies`
  - sorted `units`

The summary must not discard fields just because they do not map to Turtle yet. Its job is to show what the providers actually returned.

## 7. API Discipline

Real provider capture is opt-in:

```bash
REAL_SOURCE_VALIDATION=1 \
SAMPLE_SET=provider_field_baseline \
PROVIDERS=akshare,yahoo \
OUT_DIR=tmp/runs/provider_field_capture_baseline \
scripts/run-real-source-validation.sh
```

After one successful run, promote the output directory to a fixture directory:

```text
tests/fixtures/provider_captures/provider_field_baseline/
```

Subsequent mapping, derivation, reconciliation, and export work should use the captured `source_inventory.jsonl` and raw artifacts. Real provider calls should only be repeated when intentionally refreshing provider shapes or adding a new company/statement family.

## 8. Testing Contract

Normal tests must use fake injected clients only. They should prove:

- The capture target matrix contains the expected 18 provider/company/statement targets.
- The field inventory summary preserves unmapped raw fields.
- Adapter-backed validation writes the field inventory summary.
- `provider_field_baseline` keeps the latest five annual periods while preserving all fields inside those periods.
- Captured inventory replay can produce the same field inventory summary without clients.
- The script forwards `SAMPLE_SET=provider_field_baseline` to the Python entrypoint.

Tests must not import AKShare, yfinance, or make network calls.

## 9. Success Criteria

This stage is complete when:

- The provider field baseline sample set is available from the validation CLI/script.
- Baseline inventory is bounded to the latest five annual periods per provider/company/statement target, rather than all historical periods.
- `provider_field_inventory_summary.json` is written for adapter-backed and captured validation runs.
- A real capture command can run once and archive raw artifacts, manifest, inventory, and summary under `tmp/runs/...`.
- Successful captured outputs can be promoted into `tests/fixtures/provider_captures/provider_field_baseline/`.
- Later Turtle mapping work can inspect provider fields without calling AKShare/Yahoo again.
