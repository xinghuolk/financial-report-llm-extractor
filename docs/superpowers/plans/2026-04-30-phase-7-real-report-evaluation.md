# Phase 7 Real Report Evaluation Implementation Plan

> **For agentic workers:** Phase 7 has started with an evaluation harness. It does not yet run real PDFs end to end; it defines the matrix and summarizes extraction outputs for review.

**Goal:** Decide whether the first slice is useful on real PDFs by making report availability and extraction quality reviewable.

**Architecture:** Keep evaluation code in `src/financial_report_llm_extractor/evaluation.py`. It defines the roadmap fixture matrix, checks PDF availability, summarizes `extraction_result.json`, and writes `evaluation_summary.json`.

**Tech Stack:** Python 3.11 standard library, JSON, pytest.

---

### Task 1: Evaluation Matrix

**Files:**
- Create: `src/financial_report_llm_extractor/evaluation.py`
- Create: `tests/test_evaluation.py`

- [x] **Step 1: Write failing tests**

Cover the roadmap report IDs and PDF paths for `600519`, `00001`, and `01113`.

- [x] **Step 2: Implement minimal code**

Add `EvaluationFixture`, `DEFAULT_EVALUATION_FIXTURES`, and `build_evaluation_matrix()`.

- [x] **Step 3: Verify**

Run: `uv run pytest tests/test_evaluation.py -v`

Expected: matrix shows report IDs, absolute PDF paths, and availability.

### Task 2: Extraction Review Summary

**Files:**
- Modify: `src/financial_report_llm_extractor/evaluation.py`
- Modify: `tests/test_evaluation.py`

- [x] **Step 1: Write failing tests**

Cover present/missing/ambiguous counts, present fields without evidence, and present money fields without normalized values.

- [x] **Step 2: Implement minimal code**

Add `summarize_extraction_result()`.

- [x] **Step 3: Verify**

Run: `uv run pytest tests/test_evaluation.py -v`

Expected: summaries make reviewability issues explicit.

### Task 3: Review Artifact And CLI

**Files:**
- Modify: `src/financial_report_llm_extractor/evaluation.py`
- Modify: `src/financial_report_llm_extractor/cli.py`
- Modify: `tests/test_evaluation.py`
- Modify: `tests/test_cli.py`

- [x] **Step 1: Write failing tests**

Cover `write_review_summary()` and `financial-report-llm-extractor evaluate`.

- [x] **Step 2: Implement minimal code**

Add `EvaluationReviewResult`, `write_review_summary()`, and the `evaluate` CLI command.

- [x] **Step 3: Verify**

Run:

```bash
uv run pytest tests/test_evaluation.py -v
uv run pytest tests/test_cli.py -v
```

Expected: both pass.

### Follow-Up Work

- [ ] Run ingest/chunk/retrieve/extract on the three real roadmap PDFs.
- [ ] Decide and document expected output directories for real evaluation runs.
- [ ] Add known-hard-case regression fixtures from real outputs.
- [ ] Add a human-readable Markdown review summary alongside JSON.
- [ ] Gate optional real LLM evaluation behind explicit config/env flags.

