# Phase E Turtle Mapping, Derivation, And Coverage Gate Spec

## Goal

Build the first deterministic source-to-Turtle layer after AKShare/Yahoo inventory collection. The layer consumes fixture-backed `SourceInventoryRecord` rows and the source mapping catalog, then writes reviewable mapping and coverage artifacts without making network calls.

## Scope

In scope:

- Map source inventory rows to Turtle field IDs using catalog aliases.
- Preserve all source candidates and source evidence.
- Normalize money candidates with existing deterministic money code.
- Mark field status as `present`, `missing`, `ambiguous`, or `derived`.
- Support a minimal derived formula form: `<field_id> - <field_id>`.
- Write `turtle_mapping.json`, `source_coverage_summary.json`, and `source_coverage_summary.md`.

Out of scope:

- Real AKShare or Yahoo calls.
- Cross-source conflict resolution; Phase F owns conflict policy.
- PDF/LLM fallback execution.
- FX conversion.
- Promoting values to canonical facts.

## Requirements

- `present` mapped money candidates must have proven currency, unit, normalized value, and source evidence.
- Multiple valid direct candidates for one field must produce `ambiguous` unless deterministic reconciliation has already run.
- Missing fields must be explicit, not omitted.
- Derived fields must preserve input field IDs and source evidence lineage.
- Derived fields must only be produced when inputs are present/derived and share currency, unit, period, and scope.
- Coverage summary must count statuses and list blocker fields for missing and ambiguous mappings.

## Artifacts

Expected files under a run directory:

```text
turtle_mapping.json
source_coverage_summary.json
source_coverage_summary.md
```

## Verification

Use fixture-only tests:

```bash
uv run pytest tests/test_source_mapping.py tests/test_source_coverage.py -v
uv run ruff check .
uv run mypy src tests
```
