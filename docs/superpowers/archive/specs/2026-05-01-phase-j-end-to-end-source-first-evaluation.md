# Phase J End-To-End Source-First Evaluation Spec

## Goal

Evaluate whether the source-first path is viable before broadening implementation, using fixture-backed AKShare/Yahoo records and selected PDF evidence chunks without network calls.

## Scope

In scope:

- Run source-first evaluation for report fixtures such as `600519`, `00001`, and `01113`.
- Compare coverage for:
  - AKShare only
  - Yahoo only
  - combined
  - combined + PDF supplement
- Write per-report artifacts.
- Write top-level `evaluation_summary.json`.
- Assign remaining gaps to source availability, source mapping, PDF supplement, or LLM review.

Out of scope:

- Real AKShare/Yahoo calls.
- Real LLM calls.
- PDF ingestion/chunking execution.
- Final production readiness decision.

## Rules

- Evaluation must be deterministic and fixture-driven by default.
- Combined coverage must not hide reconciliation conflicts.
- PDF supplement must operate only on selected fields.
- Remaining gaps must be explicit and categorized.

## Verification

```bash
uv run pytest tests/test_source_first_evaluation.py -v
uv run ruff check .
uv run mypy src tests
```
