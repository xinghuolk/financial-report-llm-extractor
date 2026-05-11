# Phase H Selected PDF Evidence Supplement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reuse existing PDF retrieval to attach page/block/snippet evidence only to selected source-first fields that require PDF evidence.

**Architecture:** Add `structured_sources/pdf_supplement.py` after Phase G export. It consumes `SourceFirstExportResult`, calls existing `retrieve_candidates()` for selected fields over chunk records already produced by the PDF pipeline, writes `pdf_evidence_supplement.json`, and can return a new export result with PDF evidence attached.

**Tech Stack:** Python 3.11 standard library, dataclasses, pytest, existing `Evidence`, `retrieve_candidates()`, and source-first export dataclasses.

---

### Task 1: Build Selected PDF Evidence Supplement

**Files:**
- Create: `src/financial_report_llm_extractor/structured_sources/pdf_supplement.py`
- Test: `tests/test_pdf_evidence_supplement.py`

- [x] **Step 1: Write failing tests**

Write tests proving `build_pdf_evidence_supplement()`:

- selects only `needs_pdf_evidence` fields by default;
- uses existing retrieval over provided chunks;
- returns valid `Evidence` with page, chunk, block, and snippet.

- [x] **Step 2: Run failing tests**

Run: `uv run pytest tests/test_pdf_evidence_supplement.py::test_pdf_supplement_retrieves_evidence_for_needed_fields_only -v`
Expected: FAIL because `structured_sources.pdf_supplement` does not exist.

- [x] **Step 3: Implement minimal supplement builder**

Implement:

- `PdfEvidenceSupplementItem`
- `PdfEvidenceSupplementResult`
- `build_pdf_evidence_supplement(export_result, chunks, fields=None, limit=1)`

- [x] **Step 4: Run tests**

Run: `uv run pytest tests/test_pdf_evidence_supplement.py -v`
Expected: PASS for Task 1 tests.

### Task 2: Missing Evidence And Consistency Signal

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/pdf_supplement.py`
- Test: `tests/test_pdf_evidence_supplement.py`

- [x] **Step 1: Write failing tests**

Add tests proving:

- missing retrieval candidates produce `missing_pdf_evidence`;
- a snippet containing the source value records `consistency_status="value_mentioned"`;
- a snippet not containing the source value records `consistency_status="value_not_found_in_snippet"`.

- [x] **Step 2: Run failing tests**

Run: `uv run pytest tests/test_pdf_evidence_supplement.py -v`
Expected: FAIL for unimplemented missing/consistency handling.

- [x] **Step 3: Implement missing and consistency statuses**

Keep checks deterministic and string-based. Do not call LLM.

- [x] **Step 4: Run tests**

Run: `uv run pytest tests/test_pdf_evidence_supplement.py -v`
Expected: PASS.

### Task 3: Apply Supplement And Write Artifact

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/pdf_supplement.py`
- Test: `tests/test_pdf_evidence_supplement.py`

- [x] **Step 1: Write failing tests**

Add tests proving:

- `apply_pdf_evidence_supplement()` turns `needs_pdf_evidence` into `present` when evidence exists;
- `write_pdf_evidence_supplement()` writes `pdf_evidence_supplement.json`.

- [x] **Step 2: Run failing tests**

Run: `uv run pytest tests/test_pdf_evidence_supplement.py -v`
Expected: FAIL for unimplemented apply/write functions.

- [x] **Step 3: Implement apply/write functions**

Use existing `SourceFirstExportItem` and `SourceFirstExportResult`; keep source evidence unchanged.

- [x] **Step 4: Run tests**

Run: `uv run pytest tests/test_pdf_evidence_supplement.py -v`
Expected: PASS.

### Task 4: Verification

- [x] **Step 1: Run source-first PDF supplement tests**

```bash
uv run pytest tests/test_pdf_evidence_supplement.py tests/test_source_review_export.py tests/test_retrieval.py -v
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
