# Phase I LLM-Assisted Ambiguity Review Spec

## Goal

Use LLM only as a bounded reviewer for ambiguous source mapping and source-vs-PDF consistency, after deterministic source mapping, reconciliation, review export, and selected PDF evidence supplement have already run.

## Scope

In scope:

- Build prompt payloads for ambiguous/conflict source export items.
- Build prompt payloads for source-vs-PDF consistency issues.
- Call an injected JSON LLM client through `complete_json()`.
- Archive raw review request and raw response artifacts.
- Parse bounded review decisions.

Out of scope:

- Changing source values.
- Changing money normalization.
- Adding or modifying evidence.
- Real network tests.
- Broad PDF extraction.

## Rules

- LLM review output must not mutate `SourceFirstExportResult`.
- LLM review output must not create `present` facts.
- Every review request must include source evidence or PDF evidence relevant to the question.
- Raw responses must be archived even when parsing fails.
- Fake LLM tests are required; real LLM smoke tests remain opt-in.

## Verification

```bash
uv run pytest tests/test_llm_ambiguity_review.py -v
uv run ruff check .
uv run mypy src tests
```
