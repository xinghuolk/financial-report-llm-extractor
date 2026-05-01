# Phase G Source-First Review Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Export source-first mapping and reconciliation results into reviewable `extraction_result.json` and `review_summary.json` artifacts.

**Architecture:** Add `structured_sources/export.py` as the review/export boundary after mapping and reconciliation. It consumes existing dataclasses from Phase E/F, preserves source and PDF evidence separately, and supports `source_only` and `pdf_required` profiles.

**Tech Stack:** Python 3.11 standard library, dataclasses, Decimal, pytest.

---

### Task 1: Source-Only Review Export

**Files:**
- Create: `src/financial_report_llm_extractor/structured_sources/export.py`
- Test: `tests/test_source_review_export.py`

- [x] **Step 1: Write failing tests**

Write tests for `build_source_first_export()` proving a source-present field exports as `present` with source evidence and no PDF evidence.

- [x] **Step 2: Run failing tests**

Run: `uv run pytest tests/test_source_review_export.py::test_source_only_export_keeps_source_evidence_separate -v`
Expected: FAIL because `structured_sources.export` does not exist.

- [x] **Step 3: Implement minimal source-only export**

Implement:

- `SourceFirstExportItem`
- `SourceFirstExportResult`
- `build_source_first_export(mapping_result, reconciliation_report, profile="source_only")`

- [x] **Step 4: Run tests**

Run: `uv run pytest tests/test_source_review_export.py -v`
Expected: PASS for Task 1 tests.

### Task 2: Conflict And PDF-Required Profiles

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/export.py`
- Test: `tests/test_source_review_export.py`

- [x] **Step 1: Write failing tests**

Add tests proving:

- reconciliation conflict exports as `conflict`;
- `pdf_required` changes source-present fields without PDF evidence to `needs_pdf_evidence`;
- provided PDF evidence remains separate under `pdf_evidence`.

- [x] **Step 2: Run failing tests**

Run: `uv run pytest tests/test_source_review_export.py -v`
Expected: FAIL for unimplemented statuses or PDF evidence handling.

- [x] **Step 3: Implement profile rules**

Implement deterministic status rules from the Phase G spec.

- [x] **Step 4: Run tests**

Run: `uv run pytest tests/test_source_review_export.py -v`
Expected: PASS.

### Task 3: Artifact Writers

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/export.py`
- Test: `tests/test_source_review_export.py`

- [x] **Step 1: Write failing test**

Add a test for `write_source_first_export_artifacts(result, output_dir)` writing:

- `extraction_result.json`
- `review_summary.json`

- [x] **Step 2: Run failing test**

Run: `uv run pytest tests/test_source_review_export.py::test_write_source_first_export_artifacts_writes_review_files -v`
Expected: FAIL because writer does not exist.

- [x] **Step 3: Implement writer**

Write sorted, indented JSON artifacts.

- [x] **Step 4: Run tests**

Run: `uv run pytest tests/test_source_review_export.py -v`
Expected: PASS.

### Task 4: Verification

- [x] **Step 1: Run source-first tests**

```bash
uv run pytest tests/test_source_review_export.py tests/test_source_mapping.py tests/test_source_reconciliation.py -v
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
