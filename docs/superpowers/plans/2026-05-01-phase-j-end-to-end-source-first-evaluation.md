# Phase J End-To-End Source-First Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fixture-driven end-to-end source-first evaluation harness that compares AKShare-only, Yahoo-only, combined, and combined-plus-PDF coverage.

**Architecture:** Add `structured_sources/source_first_evaluation.py` as an orchestration layer over already implemented Phase A-I modules. It consumes source inventory fixture records and chunk fixture records, writes per-report artifacts, and writes a top-level evaluation summary with categorized remaining gaps.

**Tech Stack:** Python 3.11 standard library, dataclasses, pytest, existing source-first modules.

---

### Task 1: Evaluation Coverage Matrix

**Files:**
- Create: `src/financial_report_llm_extractor/structured_sources/source_first_evaluation.py`
- Test: `tests/test_source_first_evaluation.py`

- [x] **Step 1: Write failing tests**

Write a fixture with two fields where AKShare covers one field and Yahoo covers one field. Assert:

- AKShare-only coverage is partial;
- Yahoo-only coverage is partial;
- combined coverage is complete;
- combined + PDF supplement coverage is complete when chunks contain evidence.

- [x] **Step 2: Run failing tests**

Run: `uv run pytest tests/test_source_first_evaluation.py::test_source_first_evaluation_compares_source_coverage_modes -v`
Expected: FAIL because `source_first_evaluation.py` does not exist.

- [x] **Step 3: Implement evaluation matrix**

Implement:

- `SourceFirstEvaluationFixture`
- `run_source_first_evaluation(fixtures, catalog, output_dir)`

- [x] **Step 4: Run tests**

Run: `uv run pytest tests/test_source_first_evaluation.py -v`
Expected: PASS for Task 1 tests.

### Task 2: Remaining Gap Categorization

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/source_first_evaluation.py`
- Test: `tests/test_source_first_evaluation.py`

- [x] **Step 1: Write failing tests**

Add a fixture with one source conflict and one missing field. Assert remaining gaps are assigned to `llm_review` and `source_availability`.

- [x] **Step 2: Run failing tests**

Run: `uv run pytest tests/test_source_first_evaluation.py -v`
Expected: FAIL for missing gap categorization.

- [x] **Step 3: Implement gap categorization**

Categorize:

- `source_availability`: missing fields after combined mapping
- `source_mapping`: blocked fields after combined mapping
- `pdf_supplement`: fields still `needs_pdf_evidence`
- `llm_review`: conflict or ambiguous fields

- [x] **Step 4: Run tests**

Run: `uv run pytest tests/test_source_first_evaluation.py -v`
Expected: PASS.

### Task 3: Artifacts And Roadmap Note

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/source_first_evaluation.py`
- Modify: `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md`
- Create: `scripts/run-source-first-e2e-evaluation.sh`
- Test: `tests/test_source_first_evaluation.py`

- [x] **Step 1: Write failing tests**

Assert per-report artifacts exist:

- `source_inventory.jsonl`
- `turtle_mapping.json`
- `source_coverage_summary.json`
- `reconciliation_report.json`
- `pdf_evidence_supplement.json`
- `extraction_result.json`
- `review_summary.json`
- top-level `evaluation_summary.json`
- `scripts/run-source-first-e2e-evaluation.sh` is a local fixture-driven entrypoint.

- [x] **Step 2: Run failing tests**

Run: `uv run pytest tests/test_source_first_evaluation.py -v`
Expected: FAIL for missing artifact writes.

- [x] **Step 3: Implement artifact writes and update roadmap note**

Use existing writer functions. Update the roadmap with a short Phase J fixture-evaluation note.

- [x] **Step 4: Run tests**

Run: `uv run pytest tests/test_source_first_evaluation.py -v`
Expected: PASS.

### Task 4: Verification

- [x] **Step 1: Run source-first evaluation tests**

```bash
uv run pytest tests/test_source_first_evaluation.py tests/test_source_review_export.py tests/test_pdf_evidence_supplement.py -v
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
