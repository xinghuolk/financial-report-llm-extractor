# Phase D Yahoo Fixture Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the second structured source boundary using injected Yahoo/yfinance-like fixture clients, without importing yfinance or making network calls.

**Architecture:** Create `structured_sources/yahoo_adapter.py` with an adapter that accepts a fixture client returning statement dictionaries. It writes raw JSON artifacts and converts Yahoo standardized fields into `SourceInventoryRecord` rows tagged as source `yahoo`.

**Tech Stack:** Python 3.11 standard library, Protocol typing, pytest fixture clients, existing source artifact and inventory contracts.

---

### Task 1: Yahoo Statement Dict To Inventory

**Files:**
- Create: `src/financial_report_llm_extractor/structured_sources/yahoo_adapter.py`
- Test: `tests/test_yahoo_adapter.py`

- [x] **Step 1: Write failing tests**

Test `YahooAdapter.fetch_statement_inventory()` with a fake client exposing `get_financial_statement(ticker, statement_type)`. The fake returns rows shaped as `{"field": "Total Revenue", "period": "2024-12-31", "value": "100"}` plus metadata.

- [x] **Step 2: Run failing tests**

Run: `uv run pytest tests/test_yahoo_adapter.py -v`
Expected: FAIL because `yahoo_adapter.py` does not exist.

- [x] **Step 3: Implement minimal adapter**

Implement:

- `YahooAdapter(client, artifact_store)`
- `fetch_statement_inventory(ticker, market, statement_type, currency, unit)`

The adapter writes raw rows to `source_artifacts/yahoo/*.json`, returns `SourceInventoryRecord`, and records `function="get_financial_statement"`.

- [x] **Step 4: Run tests**

Run: `uv run pytest tests/test_yahoo_adapter.py -v`
Expected: PASS.

### Task 2: Yahoo Missing/Unsupported Status

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/yahoo_adapter.py`
- Test: `tests/test_yahoo_adapter.py`

- [x] **Step 1: Write failing tests**

Add a fake client returning an empty statement. The adapter should return one `SourceInventoryRecord` with `source_status="missing"` for the requested statement type, so downstream coverage can report Yahoo missing without treating it as a successful empty run.

- [x] **Step 2: Run failing tests**

Run: `uv run pytest tests/test_yahoo_adapter.py -v`
Expected: FAIL because empty statements currently return no records.

- [x] **Step 3: Implement missing record**

When no rows are returned, create a missing record with source evidence pointing to the raw artifact and `raw_field_name` set to `<statement_type>`.

- [x] **Step 4: Run tests**

Run: `uv run pytest tests/test_yahoo_adapter.py -v`
Expected: PASS.

### Task 3: Verification

- [x] **Step 1: Run structured source tests**

```bash
uv run pytest tests/test_yahoo_adapter.py tests/test_akshare_adapter.py tests/test_source_artifacts.py tests/test_source_coverage.py -v
```

Expected: PASS.

- [x] **Step 2: Run static checks**

```bash
uv run ruff check .
uv run mypy src tests
```

Expected: PASS.
