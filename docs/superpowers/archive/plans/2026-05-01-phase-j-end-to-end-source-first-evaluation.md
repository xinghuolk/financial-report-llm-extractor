# Phase J End-To-End Source-First Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fixture-driven end-to-end source-first evaluation harness that compares AKShare-only, Yahoo-only, combined, and combined-plus-PDF coverage.

**Architecture:** Add `structured_sources/source_first_evaluation.py` as an orchestration layer over already implemented Phase A-I modules. It consumes source inventory fixture records and chunk fixture records, writes per-report artifacts, and writes a top-level evaluation summary with categorized remaining gaps.

**Tech Stack:** Python 3.11 standard library, dataclasses, pytest, existing source-first modules.

**Current status update:** The original Phase J synthetic harness is implemented, but review found that it did not prove real AKShare/Yahoo viability. The phase now includes an additional real-source validation direction:

- Real provider calls must be opt-in and minimal.
- Provider responses should be captured into stable `source_inventory.jsonl` fixtures after the first successful call.
- Mapping, reconciliation, and export fixes should be driven from captured fixtures instead of repeated provider requests.
- The first captured AKShare 600519 income statement fixture validates source inventory -> Turtle mapping -> reconciliation -> source-only export for `revenue` and `net_profit`.
- A later captured AKShare 600519 combined fixture validates income statement, balance sheet, and cash flow through the same pipeline and covers 8 of 9 minimal fields.
- A captured Yahoo/yfinance `0001.HK` income statement fixture validates `revenue`, `net_profit`, and `gross_profit` through the same pipeline.

This plan should be read as an implementation history plus validation guardrail. Future work should not blindly repeat these tasks; instead, inspect the current captured fixture coverage, the latest `review_summary.json`, and the roadmap status to choose the next missing source/statement family.

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

### Follow-up Direction: Captured Real-Source Validation

**Files added by follow-up work:**
- `src/financial_report_llm_extractor/structured_sources/real_source_validation.py`
- `scripts/run-real-source-validation.sh`
- `tests/test_real_source_validation.py`
- `tests/fixtures/akshare/600519_income_statement_2025_required_fields.jsonl`
- `tests/fixtures/akshare/600519_combined_statements_2025_required_fields.jsonl`
- `tests/fixtures/yahoo/0001_hk_income_statement_2025_required_fields.jsonl`

**Behavior now expected:**
- `REAL_SOURCE_VALIDATION=1` gates real provider access.
- `INVENTORY_FIXTURE=<path>` replays captured source inventory without provider access.
- Captured replay writes:
  - `source_inventory.jsonl`
  - `turtle_mapping.json`
  - `source_coverage_summary.json`
  - `reconciliation_report.json`
  - `extraction_result.json`
  - `review_summary.json`
  - `real_source_validation_summary.json`
- The mapper must not report matched-but-invalid candidates as `missing`; it must use `blocked`.
- Same-source duplicate candidates may be resolved by catalog alias precedence.
- Cross-source disagreements must remain visible for reconciliation and review.

**How to choose next work:**

Run or inspect a captured validation output, then continue with the highest-value missing statement family. For the current minimal catalog, AKShare combined captured replay covers `revenue`, `net_profit`, `total_assets`, `total_liabilities`, `cash`, `operating_cash_flow`, `total_cur_assets`, and `total_cur_liab`; Yahoo income captured replay covers `revenue`, `net_profit`, and `gross_profit`.

The next validation targets are Yahoo balance sheet/cash flow captured replay and `00001`/`01113` AKShare/Yahoo captured replay. Do not repeat real provider calls unless a new statement family or ticker needs to be captured.

**Captured replay command:**

```bash
REAL_SOURCE_VALIDATION=1 \
INVENTORY_FIXTURE=tests/fixtures/akshare/600519_income_statement_2025_required_fields.jsonl \
OUT_DIR=tmp/runs/captured_source_validation_akshare \
scripts/run-real-source-validation.sh

REAL_SOURCE_VALIDATION=1 \
INVENTORY_FIXTURE=tests/fixtures/akshare/600519_combined_statements_2025_required_fields.jsonl \
OUT_DIR=tmp/runs/captured_source_validation_akshare_combined \
scripts/run-real-source-validation.sh

REAL_SOURCE_VALIDATION=1 \
INVENTORY_FIXTURE=tests/fixtures/yahoo/0001_hk_income_statement_2025_required_fields.jsonl \
OUT_DIR=tmp/runs/captured_source_validation_yahoo_income \
scripts/run-real-source-validation.sh
```

- [x] **Step 2: Run full verification**

```bash
uv run pytest -v
uv run ruff check .
uv run mypy src tests
git diff --check
```

Expected: PASS.
