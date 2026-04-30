# Phase 12-13 Real PDF Quick Validation And LLM Row Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the discovery pipeline on a real PDF without LLM, then add an opt-in real LLM row-discovery smoke path.

**Architecture:** Extend the existing quick-validation layout into an orchestrated no-network workflow. Add a parser fallback only as needed for real PDF validation. Add LLM row discovery as a separate opt-in command that consumes existing statement-map artifacts and archives prompt/raw/parsed outputs.

**Tech Stack:** Python 3.12, JSON/JSONL artifacts, existing CLI, OpenAI-compatible transport patterns, pytest, ruff, mypy.

---

## Gate Structure

This is one plan with two gates:

- **Gate A:** Phase 12 no-network real PDF quick validation works for `00001_2025_en`.
- **Gate B:** Phase 13 opt-in LLM row discovery is implemented and testable with injected transport.

Do not manually run real network calls in automated tests.

---

### Task 1: Parser Fallback Contract

**Files:**
- Modify: `src/financial_report_llm_extractor/ingestion.py`
- Create or modify: `tests/test_ingestion.py`

- [ ] Write a failing test for fallback parser selection when `pdftotext` is unavailable.
- [ ] Implement a parser resolver that prefers `PdftotextParser` and can accept or select a Python fallback parser.
- [ ] If adding a dependency is avoided, design the fallback behind an injectable parser interface and keep tests fixture-based.
- [ ] Run `uv run pytest tests/test_ingestion.py -v`.

### Task 2: Quick Validation Orchestrator

**Files:**
- Create: `src/financial_report_llm_extractor/quick_validation_runner.py`
- Create: `tests/test_quick_validation_runner.py`
- Modify: `src/financial_report_llm_extractor/cli.py`
- Modify: `tests/test_cli.py`

- [ ] Write a failing test for running a no-network quick validation with an injected parser.
- [ ] The test should assert creation of `pages.jsonl`, `chunks.jsonl`, `parser_capability.json`, `document_map.json`, `statement_map.json`, `row_inventory.json`, `catalog_mapping.json`, and `quick_validation_summary.json`.
- [ ] Implement `run_quick_validation(pdf_path, report_id, root_dir, parser=None, selected_fields=...)`.
- [ ] Add CLI command `quick-validate --pdf --report-id --root`.
- [ ] Run `uv run pytest tests/test_quick_validation_runner.py tests/test_cli.py -v`.

### Task 3: Real PDF Manual Probe

**Files:**
- No production files required unless Phase 12 exposes a real parser gap.

- [ ] Run `quick-validate` against `downloads/hk_stocks/00001/annual/2025_annual_en.pdf`.
- [ ] Inspect `parser_capability.json` and `quick_validation_summary.json`.
- [ ] If ingestion fails because no parser backend is available, stop and implement the smallest acceptable fallback.
- [ ] If document/statement map produces no formal statements, stop and improve rule detection before Phase 13.

Expected command:

```powershell
uv run financial-report-llm-extractor quick-validate --pdf downloads/hk_stocks/00001/annual/2025_annual_en.pdf --report-id 00001_2025_en --root .
```

### Task 4: LLM Row Discovery Prompt Contract

**Files:**
- Modify: `src/financial_report_llm_extractor/statement_discovery.py` or create `src/financial_report_llm_extractor/llm_row_discovery.py`
- Create: `tests/test_llm_row_discovery.py`

- [ ] Write a failing test that builds a prompt payload from one statement map entry and its chunk.
- [ ] Assert the prompt contains statement-scoped block evidence only.
- [ ] Implement prompt payload construction with prompt/schema version fields.
- [ ] Run `uv run pytest tests/test_llm_row_discovery.py -v`.

### Task 5: LLM Row Discovery Transport

**Files:**
- Modify: `src/financial_report_llm_extractor/llm_row_discovery.py`
- Modify: `tests/test_llm_row_discovery.py`

- [ ] Write a failing injected-transport test for `write_llm_row_inventory()`.
- [ ] Assert prompt payload, raw response, parsed response, and `row_inventory_llm.json` are written.
- [ ] Assert malformed JSON archives raw response and structured error.
- [ ] Implement the minimal OpenAI-compatible row discovery call, reusing existing config style.
- [ ] Run `uv run pytest tests/test_llm_row_discovery.py -v`.

### Task 6: LLM Row Discovery CLI

**Files:**
- Modify: `src/financial_report_llm_extractor/cli.py`
- Modify: `tests/test_cli.py`

- [ ] Write a failing CLI delegation test for `discover-rows-llm`.
- [ ] Add CLI args: `--chunks`, `--statement-map`, `--config`, `--out`, `--prompt-dir`, `--raw-response-dir`, `--parsed-response-dir`.
- [ ] Run `uv run pytest tests/test_cli.py tests/test_llm_row_discovery.py -v`.

### Task 7: Verification

- [ ] Run `uv run pytest -v`.
- [ ] Run `uv run ruff check .`.
- [ ] Run `uv run mypy src tests`.
- [ ] Run `git diff --check`.

### Task 8: Commit

- [ ] Commit with `feat: validate real pdf and llm row discovery`.

---

## Manual Real LLM Smoke

This is opt-in and should not block normal CI.

Prepare config:

```json
{
  "provider": "openai-compatible",
  "model": "model-name",
  "base_url": "https://example.com/v1",
  "api_key_env": "OPENAI_API_KEY",
  "timeout_seconds": 60,
  "max_retries": 1
}
```

Set key:

```powershell
$env:OPENAI_API_KEY = "..."
```

Run:

```powershell
uv run financial-report-llm-extractor discover-rows-llm --chunks tmp/runs/quick_validation/00001_2025_en/chunks.jsonl --statement-map tmp/runs/quick_validation/00001_2025_en/statement_map.json --config llm_config.json --out tmp/runs/quick_validation/00001_2025_en/row_inventory_llm.json --prompt-dir tmp/runs/quick_validation/00001_2025_en/prompt_payloads --raw-response-dir tmp/runs/quick_validation/00001_2025_en/raw_llm_responses --parsed-response-dir tmp/runs/quick_validation/00001_2025_en/parsed_llm_responses
```
