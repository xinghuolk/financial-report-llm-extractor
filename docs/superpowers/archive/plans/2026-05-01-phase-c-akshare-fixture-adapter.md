# Phase C AKShare Fixture Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add the first AKShare adapter boundary using injected fixture clients, without importing AKShare or making network calls.

**Architecture:** Create `structured_sources/akshare_adapter.py` with a small adapter that converts AKShare-like raw rows into `SourceInventoryRecord` objects and writes raw artifacts through `SourceArtifactStore`. Tests use fake clients that return lists of dictionaries shaped like AKShare/Eastmoney rows.

**Tech Stack:** Python 3.11 standard library, dataclasses/protocol-style duck typing, pytest fixtures, existing source artifact and inventory contracts.

---

### Task 1: HK Statement Rows To Inventory

**Files:**
- Create: `src/financial_report_llm_extractor/structured_sources/akshare_adapter.py`
- Test: `tests/test_akshare_adapter.py`

- [x] **Step 1: Write failing tests**

Test `AkshareAdapter.fetch_hk_statement_inventory()` with a fake client exposing:

- `stock_financial_hk_report_em(stock, symbol, indicator)`
- `stock_financial_hk_report_metadata(stock)`

Expected inventory records must include ticker, market, statement type, period, raw field name/code, amount, HKD currency, unit, account standard, report type, and source evidence.

- [x] **Step 2: Run failing tests**

Run: `uv run pytest tests/test_akshare_adapter.py -v`
Expected: FAIL because `akshare_adapter.py` does not exist.

- [x] **Step 3: Implement minimal adapter**

Implement:

- `AkshareAdapter(client, artifact_store)`
- `fetch_hk_statement_inventory(ticker, statement_type, unit="raw")`

The adapter writes raw rows to `source_artifacts/akshare/*.json`, joins metadata by `REPORT_DATE`, and returns tuple of `SourceInventoryRecord`.

- [x] **Step 4: Run tests**

Run: `uv run pytest tests/test_akshare_adapter.py -v`
Expected: PASS.

### Task 2: A-Share Statement Rows To Inventory

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/akshare_adapter.py`
- Test: `tests/test_akshare_adapter.py`

- [x] **Step 1: Write failing tests**

Test `fetch_cn_statement_inventory()` with fake client methods shaped like:

- `stock_balance_sheet_by_report_em(symbol)`
- `stock_profit_sheet_by_report_em(symbol)`
- `stock_cash_flow_sheet_by_report_em(symbol)`

Expected records should use CN market, CNY currency, provided unit, raw field names and parsed numeric values.

- [x] **Step 2: Run failing tests**

Run: `uv run pytest tests/test_akshare_adapter.py -v`
Expected: FAIL for missing CN adapter method.

- [x] **Step 3: Implement CN conversion**

Map statement types to AKShare-like function names:

- `balance_sheet` -> `stock_balance_sheet_by_report_em`
- `income_statement` -> `stock_profit_sheet_by_report_em`
- `cash_flow` -> `stock_cash_flow_sheet_by_report_em`

- [x] **Step 4: Run tests**

Run: `uv run pytest tests/test_akshare_adapter.py -v`
Expected: PASS.

### Task 3: Verification

- [x] **Step 1: Run structured source tests**

```bash
uv run pytest tests/test_akshare_adapter.py tests/test_source_artifacts.py tests/test_source_coverage.py -v
```

Expected: PASS.

- [x] **Step 2: Run static checks**

```bash
uv run ruff check .
uv run mypy src tests
```

Expected: PASS.
