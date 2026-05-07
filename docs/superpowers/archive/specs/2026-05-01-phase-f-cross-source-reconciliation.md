# Phase F Cross-Source Reconciliation Spec

## Goal

Compare mapped Turtle candidates from AKShare and Yahoo before any value is treated as source-first ready. Combined coverage must not hide source disagreement.

## Scope

In scope:

- Reconcile candidate values inside a `TurtleMappingResult`.
- Detect single-source, equivalent, close, conflict, and blocked cases.
- Compare period, currency, unit, and normalized numeric value.
- Write a deterministic `reconciliation_report.json`.

Out of scope:

- Choosing canonical facts.
- FX conversion.
- Calling AKShare/Yahoo.
- PDF/LLM fallback execution.

## Rules

- One valid candidate is `single_source`.
- Multiple candidates with different periods are `conflict`.
- Multiple candidates with different currencies are `conflict`.
- Multiple candidates with different units are `conflict`.
- Multiple candidates with equal normalized values are `equivalent`.
- Multiple candidates within configured tolerance are `close`.
- Multiple candidates outside tolerance are `conflict`.
- Missing or non-candidate fields are `blocked` with the mapped field status as the reason.

## Verification

```bash
uv run pytest tests/test_source_reconciliation.py -v
uv run ruff check .
uv run mypy src tests
```
