# Phase G Source-First Review Export Spec

## Goal

Produce reviewable source-first export artifacts from Phase E mapping and Phase F reconciliation, without running PDF fallback.

## Scope

In scope:

- Build `extraction_result.json` from `TurtleMappingResult` and `ReconciliationReport`.
- Build `review_summary.json`.
- Preserve source evidence separately from PDF evidence.
- Support two export profiles:
  - `source_only`
  - `pdf_required`
- For `pdf_required`, list fields that have source values but still need PDF page/block/snippet evidence.

Out of scope:

- PDF evidence retrieval.
- LLM review.
- Canonical fact promotion.
- FX conversion.
- Real AKShare/Yahoo calls.

## Rules

- `missing`, `ambiguous`, `conflict`, and `blocked` statuses must remain explicit.
- Source-only present fields must include source evidence.
- Derived fields may be present with source evidence inherited from inputs.
- Reconciliation conflicts must export as `conflict`.
- For `pdf_required`, a source-present field without PDF evidence exports as `needs_pdf_evidence`.
- PDF evidence must be represented under a separate `pdf_evidence` key and must not be mixed with `source_evidence`.

## Verification

```bash
uv run pytest tests/test_source_review_export.py -v
uv run ruff check .
uv run mypy src tests
```
