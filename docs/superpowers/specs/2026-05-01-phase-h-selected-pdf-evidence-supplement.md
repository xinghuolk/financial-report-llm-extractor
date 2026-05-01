# Phase H Selected PDF Evidence Supplement Spec

## Goal

Attach PDF page/block/snippet evidence only for fields selected by the source-first gate, especially fields marked `needs_pdf_evidence` by the `pdf_required` export profile.

## Scope

In scope:

- Consume `SourceFirstExportResult`.
- Select fields needing PDF evidence.
- Reuse existing `retrieve_candidates()` over already-built chunk records.
- Produce `pdf_evidence_supplement.json`.
- Convert retrieval evidence into existing `Evidence` objects.
- Apply supplemental PDF evidence back to the source-first export result.
- Record a deterministic consistency signal between source value and PDF snippet.

Out of scope:

- Running PDF ingestion/chunking.
- Broad P0/P1 PDF retrieval.
- LLM review.
- Table reconstruction.
- Changing source mapping or reconciliation decisions.

## Rules

- Default field selection is only `status == "needs_pdf_evidence"`.
- Caller may pass an explicit field list for review, but the supplement still runs selected fields only.
- Missing retrieval candidates must be explicit.
- Invalid retrieval evidence must not be silently attached.
- `source_evidence` and `pdf_evidence` remain separate.
- Applying a supplement may turn `needs_pdf_evidence` into `present` only when valid PDF evidence exists.

## Verification

```bash
uv run pytest tests/test_pdf_evidence_supplement.py -v
uv run ruff check .
uv run mypy src tests
```
