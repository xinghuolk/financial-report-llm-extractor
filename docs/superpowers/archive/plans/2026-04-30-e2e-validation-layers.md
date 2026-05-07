# E2E Validation Layers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add repeatable E2E validation for default no-network runs, local real PDFs, and opt-in real LLM smoke tests.

**Architecture:** Keep default E2E in pytest with synthetic parser input. Keep real PDF and real LLM checks as shell scripts under `scripts/` so large local files and network calls stay opt-in. Reuse existing CLI and pipeline functions instead of duplicating extraction logic.

**Tech Stack:** Python 3.11, pytest, Bash, repository CLI, JSON artifacts.

---

### Task 1: Default No-Network Pytest E2E

**Files:**
- Create: `tests/test_e2e_pipeline.py`

- [ ] Add a synthetic parser and fixture text containing income statement, balance sheet, and cash flow statement pages.
- [ ] Run the end-to-end Python pipeline into `tmp_path / "run"`.
- [ ] Assert core artifacts exist and contain non-empty statement, row, retrieval, extraction, and evaluation output.
- [ ] Run `uv run pytest tests/test_e2e_pipeline.py -v`.

### Task 2: Local Real-PDF E2E Script

**Files:**
- Create: `scripts/run-local-pdf-e2e.sh`
- Modify: `tests/test_e2e_pipeline.py`

- [ ] Add a test that the script exists and contains the required CLI commands.
- [ ] Implement a Bash script that defaults to the local 00001 English annual report.
- [ ] Run `bash -n scripts/run-local-pdf-e2e.sh`.
- [ ] Run `uv run pytest tests/test_e2e_pipeline.py -v`.

### Task 3: Real LLM Smoke Script

**Files:**
- Create: `scripts/run-real-llm-smoke.sh`
- Modify: `tests/test_e2e_pipeline.py`
- Modify: `env.example`

- [ ] Add a test that the smoke script exists and supports `deepseek`, `ollama`, and `gemini`.
- [ ] Add provider model/base URL knobs to `env.example`.
- [ ] Implement provider config generation without printing API key values.
- [ ] Run `bash -n scripts/run-real-llm-smoke.sh`.
- [ ] Run `uv run pytest tests/test_e2e_pipeline.py -v`.

### Task 4: Verification

- [ ] Run `uv run pytest -v`.
- [ ] Run `uv run ruff check .`.
- [ ] Run `uv run mypy src tests`.
- [ ] Run `git diff --check`.

### Task 5: Commit

- [ ] Commit with `test: add e2e validation layers`.
