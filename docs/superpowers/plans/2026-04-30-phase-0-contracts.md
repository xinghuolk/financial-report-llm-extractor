# Phase 0 Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish the data contracts and validation invariants needed before PDF ingestion, retrieval, or LLM calls.

**Architecture:** Keep Phase 0 inside `src/financial_report_llm_extractor/models.py` and `tests/test_models.py`. The models are frozen dataclasses with explicit validation methods; downstream components can create artifacts without importing PDF or LLM libraries.

**Tech Stack:** Python 3.11 dataclasses, `Decimal`, `typing.Literal`, pytest.

---

### Task 1: Expand Evidence And Money Contracts

**Files:**
- Modify: `src/financial_report_llm_extractor/models.py`
- Modify: `tests/test_models.py`

- [x] **Step 1: Write failing tests**

Add tests for block-level evidence and money normalization:

```python
def test_evidence_requires_page_chunk_block_and_snippet() -> None:
    with pytest.raises(ValueError, match="page must be positive"):
        Evidence(page=0, chunk_id="c1", block_id="b1", snippet="Revenue 100").validate()

    with pytest.raises(ValueError, match="block_id is required"):
        Evidence(page=1, chunk_id="c1", block_id="", snippet="Revenue 100").validate()


def test_money_amount_requires_consistent_normalized_value() -> None:
    money = MoneyAmount(
        value_raw="280,036",
        value=Decimal("280036"),
        currency="HKD",
        unit="HKD million",
        unit_multiplier=Decimal("1000000"),
        normalized_value=Decimal("280036000000"),
        normalized_unit="HKD",
    )

    money.validate()


def test_money_amount_rejects_inconsistent_normalized_value() -> None:
    money = MoneyAmount(
        value_raw="280,036",
        value=Decimal("280036"),
        currency="HKD",
        unit="HKD million",
        unit_multiplier=Decimal("1000000"),
        normalized_value=Decimal("280036"),
        normalized_unit="HKD",
    )

    with pytest.raises(ValueError, match="normalized_value must equal"):
        money.validate()
```

- [x] **Step 2: Run tests and verify red**

Run: `uv run pytest tests/test_models.py -v`

Expected: fails because `MoneyAmount` and `Evidence.block_id` do not exist yet.

- [x] **Step 3: Implement contracts**

Add `Currency`, `MoneyAmount`, and expand `Evidence` with `block_id`, optional `table_id`, `cell_id`, and `bbox`.

- [x] **Step 4: Run tests and verify green**

Run: `uv run pytest tests/test_models.py -v`

Expected: all model tests pass.

### Task 2: Add Extracted Item Money Invariants

**Files:**
- Modify: `src/financial_report_llm_extractor/models.py`
- Modify: `tests/test_models.py`

- [x] **Step 1: Write failing tests**

Add tests showing that present monetary fields require deterministic money output:

```python
def test_present_money_item_requires_money_amount() -> None:
    item = ExtractedItem(
        field_id="revenue",
        status="present",
        value_type="money",
        evidence=(Evidence(page=12, chunk_id="c12", block_id="b12", snippet="Revenue 100"),),
    )

    with pytest.raises(ValueError, match="present money items must include money"):
        item.validate()


def test_ambiguous_money_item_can_omit_money_amount() -> None:
    item = ExtractedItem(field_id="revenue", status="ambiguous", value_type="money")

    item.validate()
```

- [x] **Step 2: Run tests and verify red**

Run: `uv run pytest tests/test_models.py -v`

Expected: fails because `value_type` and `money` are not modeled.

- [x] **Step 3: Implement minimal item validation**

Add `value_type`, `money`, and validation that a `present` money item must include a valid `MoneyAmount`.

- [x] **Step 4: Run tests and verify green**

Run: `uv run pytest tests/test_models.py -v`

Expected: all model tests pass.

### Task 3: Add Chunk And Run Metadata Contracts

**Files:**
- Modify: `src/financial_report_llm_extractor/models.py`
- Modify: `tests/test_models.py`

- [x] **Step 1: Write failing tests**

Add tests for chunk page ranges and extraction-run metadata:

```python
def test_chunk_page_range_must_be_ordered() -> None:
    chunk = Chunk(
        chunk_id="stmt_cashflow_p64_p66",
        kind="statement_table",
        page_start=66,
        page_end=64,
        block_ids=("b1",),
    )

    with pytest.raises(ValueError, match="page_start must be <= page_end"):
        chunk.validate()


def test_extraction_run_requires_source_and_versions() -> None:
    run = ExtractionRun(source_pdf_hash="", parser_version="pdftotext:1", chunker_version="v1")

    with pytest.raises(ValueError, match="source_pdf_hash is required"):
        run.validate()
```

- [x] **Step 2: Run tests and verify red**

Run: `uv run pytest tests/test_models.py -v`

Expected: fails because `Chunk` and `ExtractionRun` do not exist.

- [x] **Step 3: Implement minimal contracts**

Add `Chunk` and `ExtractionRun` dataclasses with validation for ids, page ranges, block ids, and required version metadata.

- [x] **Step 4: Run tests and verify green**

Run: `uv run pytest tests/test_models.py -v`

Expected: all model tests pass.

### Task 4: Verify Phase 0

**Files:**
- Modify: no production files unless failures reveal issues.

- [x] **Step 1: Run model tests**

Run: `uv run pytest tests/test_models.py -v`

Expected: pass.

- [x] **Step 2: Run full test suite**

Run: `uv run pytest -v`

Expected: pass.
