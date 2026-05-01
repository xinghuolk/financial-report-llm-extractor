# Phase I LLM-Assisted Ambiguity Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a bounded LLM review layer for ambiguous source mapping and source-vs-PDF consistency, without letting LLM mutate extracted values or evidence.

**Architecture:** Add `structured_sources/llm_review.py` after Phase G/H. It builds deterministic review requests from `SourceFirstExportResult` and optional `PdfEvidenceSupplementResult`, calls an injected `complete_json()` client, archives raw request/response artifacts, and returns a review report.

**Tech Stack:** Python 3.11 standard library, dataclasses, Protocol, pytest, existing source-first export and PDF supplement dataclasses.

---

### Task 1: Build Review Requests

**Files:**
- Create: `src/financial_report_llm_extractor/structured_sources/llm_review.py`
- Test: `tests/test_llm_ambiguity_review.py`

- [x] **Step 1: Write failing tests**

Write tests proving `build_llm_review_requests()` creates:

- an `ambiguous_source_mapping` request for ambiguous/conflict export items;
- a `source_pdf_consistency` request for PDF supplement items with `value_not_found_in_snippet`.

- [x] **Step 2: Run failing tests**

Run: `uv run pytest tests/test_llm_ambiguity_review.py::test_build_review_requests_selects_ambiguous_and_consistency_items -v`
Expected: FAIL because `structured_sources.llm_review` does not exist.

- [x] **Step 3: Implement request builder**

Implement:

- `LlmReviewRequest`
- `build_llm_review_requests(export_result, pdf_supplement=None)`

- [x] **Step 4: Run tests**

Run: `uv run pytest tests/test_llm_ambiguity_review.py -v`
Expected: PASS for Task 1 tests.

### Task 2: Run Fake LLM Review And Archive Raw Artifacts

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/llm_review.py`
- Test: `tests/test_llm_ambiguity_review.py`

- [x] **Step 1: Write failing tests**

Add tests proving `run_llm_reviews()`:

- calls injected `complete_json()` with deterministic system prompt and payload;
- writes raw request/response artifacts;
- parses bounded decisions.

- [x] **Step 2: Run failing tests**

Run: `uv run pytest tests/test_llm_ambiguity_review.py -v`
Expected: FAIL for unimplemented runner.

- [x] **Step 3: Implement runner**

Implement:

- `LlmReviewDecision`
- `LlmReviewReport`
- `run_llm_reviews(requests, client, raw_response_dir)`

- [x] **Step 4: Run tests**

Run: `uv run pytest tests/test_llm_ambiguity_review.py -v`
Expected: PASS.

### Task 3: Parsing Failures Stay Review-Only

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/llm_review.py`
- Test: `tests/test_llm_ambiguity_review.py`

- [x] **Step 1: Write failing test**

Add a test proving malformed LLM response becomes `not_reviewed`, records errors, and still archives raw response.

- [x] **Step 2: Run failing test**

Run: `uv run pytest tests/test_llm_ambiguity_review.py::test_run_llm_reviews_archives_malformed_response_and_marks_not_reviewed -v`
Expected: FAIL for unimplemented malformed handling.

- [x] **Step 3: Implement malformed handling**

Do not mutate export result. The review report is advisory only.

- [x] **Step 4: Run tests**

Run: `uv run pytest tests/test_llm_ambiguity_review.py -v`
Expected: PASS.

### Task 4: Verification

- [x] **Step 1: Run LLM review tests**

```bash
uv run pytest tests/test_llm_ambiguity_review.py tests/test_source_review_export.py tests/test_pdf_evidence_supplement.py -v
```

Expected: PASS.

- [x] **Step 2: Run full verification**

```bash
uv run pytest -v
uv run ruff check .
uv run mypy src tests
git diff --check
```

Expected: PASS.
