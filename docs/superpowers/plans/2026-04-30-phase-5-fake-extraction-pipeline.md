# Phase 5 Fake Extraction Pipeline Implementation Plan

> **For agentic workers:** Phase 5 has started with a fixture-backed fake LLM pipeline. Continue from the follow-up items before adding real LLM transport.

**Goal:** Run the extraction contract end to end without network dependency.

**Architecture:** Keep fake extraction orchestration in `src/financial_report_llm_extractor/extraction.py`. It consumes `retrieval_probe.json`, calls an injected LLM-like client, normalizes money, validates `ExtractedItem`, and writes `extraction_result.json`.

**Tech Stack:** Python 3.11 standard library, dataclasses, JSON, pytest.

---

### Task 1: Prompt And Fake Client Contracts

**Files:**
- Create: `src/financial_report_llm_extractor/extraction.py`
- Create: `tests/test_extraction.py`

- [x] **Step 1: Write failing tests**

Cover `PromptRequest`, `LlmExtractedField`, `LlmResponse`, and fixture-backed `FakeLlmClient`.

- [x] **Step 2: Implement minimal code**

Add prompt/response dataclasses and `FakeLlmClient.extract()`.

- [x] **Step 3: Verify**

Run: `uv run pytest tests/test_extraction.py -v`

Expected: fake client returns fixture responses by field id.

### Task 2: Fake Extraction Orchestrator

**Files:**
- Modify: `src/financial_report_llm_extractor/extraction.py`
- Modify: `tests/test_extraction.py`

- [x] **Step 1: Write failing tests**

Cover retrieval probe -> fake LLM response -> money normalizer -> validated output JSON.

- [x] **Step 2: Implement minimal code**

Add `run_fake_extraction()` and JSON serialization for extracted items.

- [x] **Step 3: Verify**

Run: `uv run pytest tests/test_extraction.py -v`

Expected: present monetary fields contain normalized money and concrete evidence.

### Task 3: Invalid Response Handling

**Files:**
- Modify: `src/financial_report_llm_extractor/extraction.py`
- Modify: `tests/test_extraction.py`

- [x] **Step 1: Write failing tests**

Cover fake responses that claim `present` without available evidence.

- [x] **Step 2: Implement minimal code**

Downgrade invalid items to `extraction_failed` and preserve validation errors.

- [x] **Step 3: Verify**

Run: `uv run pytest tests/test_extraction.py -v`

Expected: `present` without evidence cannot pass.

### Task 4: CLI Command

**Files:**
- Modify: `src/financial_report_llm_extractor/cli.py`
- Modify: `tests/test_cli.py`

- [x] **Step 1: Write failing tests**

Cover `main(["extract-fake", "--retrieval-probe", "...", "--out", "..."])`.

- [x] **Step 2: Implement minimal code**

Add the `extract-fake` subcommand.

- [x] **Step 3: Verify**

Run: `uv run pytest tests/test_cli.py -v`

Expected: CLI command calls the extraction layer.

### Follow-Up Work

- [ ] Load fake LLM fixture responses from JSON files instead of passing only injected clients in tests.
- [ ] Support non-money value types and text outputs.
- [ ] Preserve raw LLM response artifacts for review.
- [ ] Add stricter schema validation for fake responses.
- [ ] Integrate derived values after the derived-value engine exists.

