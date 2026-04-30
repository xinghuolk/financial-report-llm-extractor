# Phase 2 Logical Chunks Implementation Plan

> **For agentic workers:** Phase 2 has started with a minimal, tested foundation. Continue from the unchecked follow-up items rather than replacing the existing implementation.

**Goal:** Create concrete evidence blocks and logical statement chunks from page-level ingestion artifacts without requiring full table reconstruction.

**Architecture:** Keep this phase in `src/financial_report_llm_extractor/chunking.py` and `tests/test_chunking.py`. `ingestion.py` remains responsible only for PDF/page artifacts. `cli.py` exposes a thin `chunk` command.

**Tech Stack:** Python 3.11 standard library, dataclasses, JSON/JSONL, pytest.

---

### Task 1: Stable Page Blocks

**Files:**
- Create: `src/financial_report_llm_extractor/chunking.py`
- Create: `tests/test_chunking.py`

- [x] **Step 1: Write failing tests**

Cover splitting `PageRecord` text into deterministic `BlockRecord` items with stable IDs such as `p0012_b0001`.

- [x] **Step 2: Run tests and verify red**

Run: `uv run pytest tests/test_chunking.py -v`

Expected: fails because `chunking.py` does not exist.

- [x] **Step 3: Implement minimal code**

Add `BlockRecord`, `split_page_blocks()`, stable block IDs, and statement-title paragraph merge.

- [x] **Step 4: Run tests and verify green**

Run: `uv run pytest tests/test_chunking.py -v`

Expected: chunking tests pass.

### Task 2: Statement Chunk Detection

**Files:**
- Modify: `src/financial_report_llm_extractor/chunking.py`
- Modify: `tests/test_chunking.py`

- [x] **Step 1: Write failing tests**

Cover Chinese and English statement-title detection for balance sheet, income statement, and cash-flow statement.

- [x] **Step 2: Implement minimal code**

Add `detect_statement_kind()` and build page chunks plus statement chunks from block sequences.

- [x] **Step 3: Verify**

Run: `uv run pytest tests/test_chunking.py -v`

Expected: statement chunks include stable IDs such as `stmt_balance_sheet_p0001_p0002`.

### Task 3: Chunk Store Artifact

**Files:**
- Modify: `src/financial_report_llm_extractor/chunking.py`
- Modify: `tests/test_chunking.py`

- [x] **Step 1: Write failing tests**

Cover `pages.jsonl` + `run_metadata.json` -> `chunks.jsonl` with source hash and metadata artifact update.

- [x] **Step 2: Implement minimal code**

Add `ChunkStore`, `ChunkStoreResult`, and `build_chunk_store()`.

- [x] **Step 3: Verify**

Run: `uv run pytest tests/test_chunking.py -v`

Expected: `chunks.jsonl` contains block and chunk records, and metadata uses `phase2-logical-chunks-v1`.

### Task 4: CLI Command

**Files:**
- Modify: `src/financial_report_llm_extractor/cli.py`
- Modify: `tests/test_cli.py`

- [x] **Step 1: Write failing tests**

Cover `main(["chunk", "--pages", "...", "--metadata", "...", "--out", "..."])` calling the chunking layer.

- [x] **Step 2: Implement minimal code**

Add the `chunk` subcommand and print block/chunk counts plus `chunks_path`.

- [x] **Step 3: Verify**

Run: `uv run pytest tests/test_cli.py -v`

Expected: CLI tests pass.

### Task 5: Verify Phase 2 Foundation

- [x] **Step 1: Run focused tests**

Run:

```bash
uv run pytest tests/test_chunking.py -v
uv run pytest tests/test_cli.py -v
```

Expected: pass.

- [x] **Step 2: Run full verification**

Run:

```bash
uv run pytest -v
uv run ruff check .
uv run mypy src tests
```

Expected: all pass.

### Follow-Up Work

- [ ] Add richer layout-line metadata when parser output includes coordinates.
- [ ] Improve continuation handling with explicit statement end heuristics.
- [ ] Add HK side-by-side statement splitting by layout column or statement region.
- [ ] Add candidate row label, period, and unit-context extraction to evidence blocks.
- [ ] Evaluate against real annual reports such as `600519`, `00001`, and `01113`.

