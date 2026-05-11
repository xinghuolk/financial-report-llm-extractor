# Phase 1 PDF Probe And Page Store Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a minimal PDF ingestion path that turns one local PDF into durable page-level JSON artifacts with source hash and parser metadata.

**Architecture:** Keep ingestion independent from retrieval and LLM. `ingestion.py` owns PDF text extraction, page splitting, hashing, and artifact writing. `cli.py` provides a thin `ingest` command. Tests use fake parser output and temporary files, so they do not require real PDFs or `pdftotext`.

**Tech Stack:** Python 3.11, dataclasses, pathlib, hashlib, json/jsonl, subprocess, pytest.

---

### Task 1: Page Text Splitting And Source Hash

**Files:**
- Create: `src/financial_report_llm_extractor/ingestion.py`
- Create: `tests/test_ingestion.py`

- [x] **Step 1: Write failing tests**

Cover splitting `pdftotext` form-feed output into page records and computing a SHA-256 source hash.

- [x] **Step 2: Run tests and verify red**

Run: `uv run pytest tests/test_ingestion.py -v`

Expected: fail because `ingestion.py` does not exist.

- [x] **Step 3: Implement minimal code**

Add `PageRecord`, `split_pdftotext_pages()`, and `compute_sha256()`.

- [x] **Step 4: Run tests and verify green**

Run: `uv run pytest tests/test_ingestion.py -v`

Expected: pass.

### Task 2: Ingest Artifacts

**Files:**
- Modify: `src/financial_report_llm_extractor/ingestion.py`
- Modify: `tests/test_ingestion.py`

- [x] **Step 1: Write failing tests**

Cover `ingest_pdf()` writing `pages.jsonl` and `run_metadata.json` using an injected fake parser.

- [x] **Step 2: Run tests and verify red**

Run: `uv run pytest tests/test_ingestion.py -v`

Expected: fail because `ingest_pdf()` does not exist.

- [x] **Step 3: Implement minimal code**

Add parser protocol, `PdftotextParser`, `IngestResult`, and `ingest_pdf()`.

- [x] **Step 4: Run tests and verify green**

Run: `uv run pytest tests/test_ingestion.py -v`

Expected: pass.

### Task 3: CLI Ingest Command

**Files:**
- Create: `src/financial_report_llm_extractor/cli.py`
- Modify: `pyproject.toml`
- Create or modify: `tests/test_cli.py`

- [x] **Step 1: Write failing tests**

Cover `main(["ingest", "--pdf", "...", "--out", "..."])` calling the ingestion layer and returning `0`.

- [x] **Step 2: Run tests and verify red**

Run: `uv run pytest tests/test_cli.py -v`

Expected: fail because `cli.py` does not exist.

- [x] **Step 3: Implement minimal code**

Add argparse CLI and project script entry point.

- [x] **Step 4: Run tests and verify green**

Run: `uv run pytest tests/test_cli.py -v`

Expected: pass.

### Task 4: Verify Phase 1

**Files:**
- Modify: no production files unless verification reveals issues.

- [x] **Step 1: Run ingestion and CLI tests**

Run: `uv run pytest tests/test_ingestion.py tests/test_cli.py -v`

Expected: pass.

- [x] **Step 2: Run full verification**

Run:

```bash
uv run pytest -v
uv run ruff check .
uv run mypy src tests
```

Expected: all pass.
