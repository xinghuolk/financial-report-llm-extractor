# Phase 3 Retrieval Probe Implementation Plan

> **For agentic workers:** Phase 3 has started with a minimal retrieval probe. Continue from the follow-up items before adding LLM behavior.

**Goal:** Retrieve candidate evidence for P0/P1 fields from `chunks.jsonl` without calling an LLM.

**Architecture:** Keep retrieval in `src/financial_report_llm_extractor/retrieval.py`. It reads field catalog JSON and chunk artifacts, scores candidate chunks, and writes `retrieval_probe.json`. `cli.py` exposes a thin `retrieve` command.

**Tech Stack:** Python 3.11 standard library, dataclasses, JSON/JSONL, pytest.

---

### Task 1: Field Specs And Hints

**Files:**
- Create: `src/financial_report_llm_extractor/retrieval.py`
- Create: `tests/test_retrieval.py`

- [x] **Step 1: Write failing tests**

Cover loading P0/P1 fields from the catalog and enriching core fields with aliases and statement hints.

- [x] **Step 2: Implement minimal code**

Add `FieldSpec`, `load_field_specs()`, and a small `FIELD_HINTS` table for core P0/P1 fields.

- [x] **Step 3: Verify**

Run: `uv run pytest tests/test_retrieval.py -v`

Expected: field specs include aliases such as `营业收入` and statement hints such as `income_statement`.

### Task 2: Candidate Scoring

**Files:**
- Modify: `src/financial_report_llm_extractor/retrieval.py`
- Modify: `tests/test_retrieval.py`

- [x] **Step 1: Write failing tests**

Cover alias matching, statement-kind bonus, evidence fields, and snippet selection.

- [x] **Step 2: Implement minimal code**

Add `RetrievalCandidate`, `retrieve_candidates()`, longest-alias de-duplication, and evidence construction.

- [x] **Step 3: Verify**

Run: `uv run pytest tests/test_retrieval.py -v`

Expected: statement-table matches rank ahead of generic page-text matches.

### Task 3: Retrieval Probe Artifact

**Files:**
- Modify: `src/financial_report_llm_extractor/retrieval.py`
- Modify: `tests/test_retrieval.py`

- [x] **Step 1: Write failing tests**

Cover `catalog.json` + `chunks.jsonl` -> `retrieval_probe.json`, including explicit `missing` fields.

- [x] **Step 2: Implement minimal code**

Add `RetrievalProbeResult` and `write_retrieval_probe()`.

- [x] **Step 3: Verify**

Run: `uv run pytest tests/test_retrieval.py -v`

Expected: output contains catalog metadata, source hash, field statuses, and candidate evidence.

### Task 4: CLI Command

**Files:**
- Modify: `src/financial_report_llm_extractor/cli.py`
- Modify: `tests/test_cli.py`

- [x] **Step 1: Write failing tests**

Cover `main(["retrieve", "--catalog", "...", "--chunks", "...", "--out", "...", "--priorities", "P0,P1"])` calling the retrieval layer.

- [x] **Step 2: Implement minimal code**

Add the `retrieve` subcommand and print field count plus output path.

- [x] **Step 3: Verify**

Run: `uv run pytest tests/test_cli.py -v`

Expected: CLI tests pass.

### Follow-Up Work

- [ ] Move aliases/hints into a richer catalog artifact instead of keeping the seed table only in code.
- [ ] Add aliases for all P0/P1 fields, especially HK wording variants.
- [ ] Score block-level evidence separately from chunk-level evidence.
- [ ] Mark known derived fields explicitly instead of only `missing`.
- [ ] Evaluate retrieval quality on real `600519`, `00001`, and `01113` reports.

