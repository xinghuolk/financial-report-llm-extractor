# Phase 10 Parser Capability Probe And Document Map Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce `parser_capability.json` and `document_map.json` from existing page/chunk artifacts so Phase 11 can start from formal statement regions.

**Architecture:** Add a focused `document_map.py` module. It reads existing JSONL artifacts, computes parser quality signals from page text, and builds a rule-first document section map from block records. CLI commands are thin delegators.

**Tech Stack:** Python 3.12, dataclasses, JSON/JSONL artifacts, pytest, ruff, mypy.

---

### Task 1: Parser Capability Probe

**Files:**
- Create: `src/financial_report_llm_extractor/document_map.py`
- Create: `tests/test_document_map.py`

- [x] Write a failing test for `write_parser_capability_probe()`.
- [x] Run the focused test and confirm it fails because the module/function is missing.
- [x] Implement the minimal parser probe writer.
- [x] Run `uv run pytest tests/test_document_map.py -v`.

### Task 2: Rule-First Document Map

**Files:**
- Modify: `src/financial_report_llm_extractor/document_map.py`
- Modify: `tests/test_document_map.py`

- [x] Write a failing test with synthetic block records for contents, financial summary, MD&A, auditor report, formal statements, and notes.
- [x] Run the focused test and confirm it fails.
- [x] Implement section detection and `write_document_map()`.
- [x] Run `uv run pytest tests/test_document_map.py -v`.

### Task 3: CLI Commands

**Files:**
- Modify: `src/financial_report_llm_extractor/cli.py`
- Modify: `tests/test_cli.py`

- [x] Write failing CLI delegation tests for `probe-parser` and `map-document`.
- [x] Run the focused CLI tests and confirm they fail.
- [x] Add parser definitions and command handlers.
- [x] Run `uv run pytest tests/test_cli.py -v`.

### Task 4: Verification And Commit

- [x] Run `uv run pytest -v`.
- [x] Run `uv run ruff check .`.
- [x] Run `uv run mypy src tests`.
- [x] Commit with `feat: add parser probe document map demo`.
