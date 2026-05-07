# Phase B Source Artifact Store Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Build the offline source artifact and inventory persistence layer needed before AKShare/Yahoo adapters.

**Architecture:** Add a focused artifact module under `structured_sources` that writes deterministic raw JSON artifacts and source inventory JSONL. It only consumes fixture data and existing dataclasses; no real source APIs are imported or called.

**Tech Stack:** Python 3.11 standard library, `json`, `pathlib`, frozen dataclasses, pytest.

---

### Task 1: Raw Source Artifact Store

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/models.py`
- Create: `src/financial_report_llm_extractor/structured_sources/artifacts.py`
- Test: `tests/test_source_artifacts.py`

- [x] **Step 1: Write failing tests**

Add tests that assert raw JSON artifacts are written under `<root>/<source>/<artifact_id>.json`, directories are created, and metadata records the source/path/content type.

- [x] **Step 2: Run failing tests**

Run: `uv run pytest tests/test_source_artifacts.py -v`
Expected: FAIL because `artifacts.py` and `SourceArtifact` do not exist.

- [x] **Step 3: Implement minimal artifact store**

Add `SourceArtifact` to `models.py` and implement:

- `build_artifact_id(source, market, ticker, artifact_type)`
- `SourceArtifactStore.write_json(source, artifact_id, payload)`

- [x] **Step 4: Run tests**

Run: `uv run pytest tests/test_source_artifacts.py -v`
Expected: PASS.

### Task 2: Source Inventory JSONL

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/artifacts.py`
- Test: `tests/test_source_artifacts.py`

- [x] **Step 1: Write failing tests**

Add tests for `write_source_inventory()` and `read_source_inventory()` roundtrip with `Decimal` values and nested `SourceEvidence`.

- [x] **Step 2: Run failing tests**

Run: `uv run pytest tests/test_source_artifacts.py -v`
Expected: FAIL because JSONL helpers do not exist.

- [x] **Step 3: Implement JSONL helpers**

Implement:

- `write_source_inventory(path, records)`
- `read_source_inventory(path)`

The writer creates parent directories and serializes one record per line. The reader reconstructs `SourceInventoryRecord` with `Decimal` and `SourceEvidence`.

- [x] **Step 4: Run tests**

Run: `uv run pytest tests/test_source_artifacts.py -v`
Expected: PASS.

### Task 3: Verification

**Files:**
- Verify all files touched in Phase B.

- [x] **Step 1: Run structured source tests**

Run:

```bash
uv run pytest tests/test_source_artifacts.py tests/test_structured_source_models.py tests/test_source_mapping_catalog.py tests/test_source_coverage.py -v
```

Expected: PASS.

- [x] **Step 2: Run static checks**

Run:

```bash
uv run ruff check .
uv run mypy src tests
```

Expected: PASS.
