# Phase F Cross-Source Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic cross-source reconciliation so AKShare/Yahoo agreement and conflict are explicit before PDF/LLM fallback.

**Architecture:** Create `structured_sources/reconciliation.py` that consumes `TurtleMappingResult` from Phase E. It compares candidates per field, emits per-field reconciliation items, and writes `reconciliation_report.json`.

**Tech Stack:** Python 3.11 standard library, dataclasses, Decimal, pytest.

---

### Task 1: Reconcile Equivalent And Conflict Values

**Files:**
- Create: `src/financial_report_llm_extractor/structured_sources/reconciliation.py`
- Test: `tests/test_source_reconciliation.py`

- [x] **Step 1: Write failing tests**

Create tests that build a `TurtleMappingResult` from two source candidates:

- equal normalized values -> `equivalent`;
- different normalized values beyond tolerance -> `conflict`.

- [x] **Step 2: Run failing tests**

Run: `uv run pytest tests/test_source_reconciliation.py::test_reconcile_marks_equal_candidates_equivalent tests/test_source_reconciliation.py::test_reconcile_marks_different_values_conflict -v`
Expected: FAIL because `structured_sources.reconciliation` does not exist.

- [x] **Step 3: Implement minimal reconciliation**

Implement:

- `ReconciliationItem`
- `ReconciliationReport`
- `reconcile_mapped_fields(result, tolerance=Decimal("0"))`

Compare normalized values after confirming period, currency, and unit match.

- [x] **Step 4: Run tests**

Run: `uv run pytest tests/test_source_reconciliation.py -v`
Expected: PASS.

### Task 2: Close, Single Source, And Metadata Conflicts

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/reconciliation.py`
- Test: `tests/test_source_reconciliation.py`

- [x] **Step 1: Write failing tests**

Add tests for:

- values within tolerance -> `close`;
- one candidate -> `single_source`;
- different period/currency/unit -> `conflict`.

- [x] **Step 2: Run failing tests**

Run: `uv run pytest tests/test_source_reconciliation.py -v`
Expected: FAIL for unimplemented statuses.

- [x] **Step 3: Implement full field status handling**

Implement deterministic status rules from the spec.

- [x] **Step 4: Run tests**

Run: `uv run pytest tests/test_source_reconciliation.py -v`
Expected: PASS.

### Task 3: Reconciliation Report Writer

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/reconciliation.py`
- Test: `tests/test_source_reconciliation.py`

- [x] **Step 1: Write failing test**

Add a test for `write_reconciliation_report(report, output_path)` writing deterministic JSON with status counts and conflict fields.

- [x] **Step 2: Run failing test**

Run: `uv run pytest tests/test_source_reconciliation.py::test_write_reconciliation_report_writes_json -v`
Expected: FAIL because writer does not exist.

- [x] **Step 3: Implement writer**

Write sorted, indented JSON with:

- `catalog_id`
- `catalog_version`
- `status_counts`
- `conflict_fields`
- `items`

- [x] **Step 4: Run tests**

Run: `uv run pytest tests/test_source_reconciliation.py -v`
Expected: PASS.

### Task 4: Verification

- [x] **Step 1: Run source-first tests**

```bash
uv run pytest tests/test_source_mapping.py tests/test_source_reconciliation.py tests/test_source_coverage.py -v
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
