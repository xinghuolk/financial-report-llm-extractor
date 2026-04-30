# Phase 11 Statement/Row Discovery To Selected-Field Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `statement_map.json`, `row_inventory.json`, and `catalog_mapping.json` demo artifacts from existing chunks/document-map outputs.

**Architecture:** Add `statement_discovery.py` as a focused module. It reads chunk records and document map sections, detects formal statement chunks, parses simple rows, and maps selected fields with deterministic aliases.

**Tech Stack:** Python 3.12, JSON/JSONL artifacts, pytest, ruff, mypy.

---

### Task 1: Statement Map

- [x] Write failing tests for `write_statement_map()`.
- [x] Implement formal statement detection inside audited financial statement pages.
- [x] Run `uv run pytest tests/test_statement_discovery.py -v`.

### Task 2: Row Inventory

- [x] Write failing tests for `write_row_inventory()`.
- [x] Implement simple row parsing from statement chunk lines.
- [x] Run `uv run pytest tests/test_statement_discovery.py -v`.

### Task 3: Catalog Mapping

- [x] Write failing tests for `write_catalog_mapping()`.
- [x] Implement deterministic selected-field mapping with explicit missing status.
- [x] Run `uv run pytest tests/test_statement_discovery.py -v`.

### Task 4: CLI

- [x] Write failing CLI delegation tests for `map-statements`, `discover-rows`, and `map-fields`.
- [x] Add CLI parser and handlers.
- [x] Run `uv run pytest tests/test_cli.py tests/test_statement_discovery.py -v`.

### Task 5: Verification And Commit

- [x] Run `uv run pytest -v`.
- [x] Run `uv run ruff check .`.
- [x] Run `uv run mypy src tests`.
- [x] Commit with `feat: add statement row discovery demo`.
