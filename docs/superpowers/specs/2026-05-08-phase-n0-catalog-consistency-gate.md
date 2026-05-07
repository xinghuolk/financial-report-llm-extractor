# Phase N0: Catalog Consistency Gate Spec

> Date: 2026-05-08
> Status: Draft
> Roadmap phase: Phase N0 (prerequisite for N1/N2/N3)

## Goal

Add automated cross-catalog consistency checks before Phase N expansion adds 18 more field entries across 5 JSON catalog files. Without automation, the implicit invariants between catalogs become harder to maintain at the 33-field denominator.

## Background

Five field_catalog JSON files have implicit consistency constraints that are currently enforced only by scattered tests:

```
turtle_v015_field_taxonomy.json        — 62 fields, full Turtle definitions
turtle_v015_coverage_matrix.json       — 62 fields, planned coverage routes
turtle_v015_source_mapping_minimal.json — 15 fields (will grow to 33)
provider_raw_semantics_hk.json          — 11 rules (post-M5)
hk_yahoo_trust_policy.json              — 8 rules (post-M5)
```

## Required Invariants

The new test must verify:

### Invariant 1: source_mapping ↔ coverage_matrix alignment

For every `field_id` in `source_mappings`:
- Field must exist in `coverage_matrix.fields`
- `source_mapping.primary_route` must equal `coverage_matrix.primary_route`
- `source_mapping.verification_status` must equal `coverage_matrix.verification`

### Invariant 2: source_mapping ↔ taxonomy alignment

For every `field_id` in `source_mappings`:
- Field must exist in `taxonomy.fields`
- `source_mapping.statement_type` must equal `taxonomy.statement_type` (where taxonomy defines it)
- `source_mapping.value_type` must equal `taxonomy.value_type`

### Invariant 3: provider_semantics ↔ source_mapping alignment

For every rule in `provider_raw_semantics_hk.json`:
- `rule.turtle_field_id` must exist in `source_mappings`
- If `rule.allowed_as_primary == true`:
  - The corresponding source_mapping entry must include `rule.raw_field_name` in `source_aliases[rule.provider]`

### Invariant 4: trust_policy ↔ source_mapping alignment

For every rule in `hk_yahoo_trust_policy.json`:
- `rule.field_id` must exist in `source_mappings`
- All entries in `rule.allowed_yahoo_raw_fields` must appear in source_mapping `source_aliases.yahoo`

### Invariant 5: trust_policy ↔ provider_semantics alignment

For every rule in `hk_yahoo_trust_policy.json` with `classification == "yahoo_pdf_verified"`:
- For each entry in `allowed_yahoo_raw_fields`:
  - There must exist a provider_semantics rule with matching `provider == "yahoo"`, `market == "HK"`, `turtle_field_id == rule.field_id`, `raw_field_name` matching, and `allowed_as_primary == true`

### Invariant 6: priority list ↔ source_mapping (forward direction only)

For every field in `turtle_v015_priority_fields.json` priorities P0/P1 that is also in `source_mappings`:
- Its `priority` field must match.

(We don't require all P0/P1 fields to be in source_mappings — that's the Phase N expansion progress signal.)

## Out of Scope

- Validating taxonomy/coverage_matrix internal consistency (already covered by existing tests).
- Validating that all 62 taxonomy fields have priorities (some may be P3/P4).
- Auto-fixing inconsistencies — the test fails fast with stable error messages.

## Test File Location

`tests/test_catalog_consistency.py`

## Test Style

Follow existing pytest patterns:
- Use real catalog files at `field_catalog/*.json`
- Use existing loader functions (`load_source_mapping_catalog`, `load_provider_semantics_catalog`, `load_hk_yahoo_trust_policy`, `load_coverage_matrix`)
- One focused test per invariant (6 tests total)
- Fail with clear assertion messages identifying the offending field/rule

## Verification

```bash
uv run pytest tests/test_catalog_consistency.py -v
uv run pytest -v
uv run ruff check .
```

All current 438 tests must continue to pass — N0 only adds new tests, doesn't modify catalog files or runtime code.
