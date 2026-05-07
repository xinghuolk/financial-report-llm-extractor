# Phase A Source Mapping Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Build the first source-first foundation: Turtle source mapping contracts, catalog loading, fixture inventory coverage, and blocking rules without calling AKShare/Yahoo.

**Architecture:** Add a small `structured_sources` package with serializable dataclass contracts, catalog parsing, and source coverage evaluation. This phase is offline only: tests use fixture dictionaries and do not import or call AKShare/yfinance.

**Tech Stack:** Python 3.11 standard library, frozen dataclasses, pytest, existing project package layout under `src/financial_report_llm_extractor/`.

---

### Task 1: Source Contract Models

**Files:**
- Create: `src/financial_report_llm_extractor/structured_sources/__init__.py`
- Create: `src/financial_report_llm_extractor/structured_sources/models.py`
- Test: `tests/test_structured_source_models.py`

- [x] **Step 1: Write failing model tests**

```python
from decimal import Decimal

import pytest

from financial_report_llm_extractor.structured_sources.models import (
    SourceEvidence,
    SourceInventoryRecord,
)


def test_source_evidence_requires_artifact_and_raw_record() -> None:
    evidence = SourceEvidence(
        source="akshare",
        adapter="akshare",
        function="stock_financial_hk_report_em",
        artifact_id="artifact-1",
        raw_record_id="00001:balance_sheet:2024",
        raw_field_name="Total assets",
    )

    evidence.validate()
    assert evidence.to_dict()["source"] == "akshare"


def test_source_inventory_money_requires_currency_and_unit() -> None:
    record = SourceInventoryRecord(
        source="akshare",
        market="HK",
        ticker="00001",
        statement_type="balance_sheet",
        period="2024-12-31",
        raw_field_name="Total assets",
        raw_value="100",
        parsed_numeric_value=Decimal("100"),
        value_type="money",
        currency="unknown",
        unit=None,
        source_evidence=(
            SourceEvidence(
                source="akshare",
                adapter="akshare",
                function="stock_financial_hk_report_em",
                artifact_id="artifact-1",
                raw_record_id="00001:balance_sheet:2024",
                raw_field_name="Total assets",
            ),
        ),
    )

    with pytest.raises(ValueError, match="money source records require currency and unit"):
        record.validate()
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_structured_source_models.py -v`
Expected: FAIL because `financial_report_llm_extractor.structured_sources` does not exist.

- [x] **Step 3: Implement minimal models**

Create frozen dataclasses:

```python
SourceName = Literal["akshare", "yahoo", "fixture"]
SourceStatus = Literal["present", "missing", "ambiguous", "source_error", "unsupported"]
SourceValueType = Literal["money", "number", "percent", "text", "derived"]

@dataclass(frozen=True)
class SourceEvidence:
    source: SourceName
    adapter: str
    function: str
    artifact_id: str
    raw_record_id: str
    raw_field_name: str
    raw_field_code: str | None = None
    retrieved_at: str | None = None
    provider_version: str | None = None

@dataclass(frozen=True)
class SourceInventoryRecord:
    source: SourceName
    market: str
    ticker: str
    statement_type: str
    period: str | None
    raw_field_name: str
    raw_value: str | int | float | None
    parsed_numeric_value: Decimal | None = None
    value_type: SourceValueType = "money"
    source_status: SourceStatus = "present"
    report_type: str | None = None
    fiscal_year: str | None = None
    scope: str = "unknown"
    account_standard: str | None = None
    currency: Currency = "unknown"
    unit: str | None = None
    raw_field_code: str | None = None
    source_evidence: tuple[SourceEvidence, ...] = field(default_factory=tuple)
```

- [x] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_structured_source_models.py -v`
Expected: PASS.

### Task 2: Source Mapping Catalog Loader

**Files:**
- Create: `src/financial_report_llm_extractor/structured_sources/catalog.py`
- Test: `tests/test_source_mapping_catalog.py`

- [x] **Step 1: Write failing catalog tests**

```python
import json
from pathlib import Path

from financial_report_llm_extractor.structured_sources.catalog import (
    load_source_mapping_catalog,
)


def test_load_source_mapping_catalog_expands_priority_fields(tmp_path: Path) -> None:
    path = tmp_path / "catalog.json"
    path.write_text(
        json.dumps(
            {
                "catalog_id": "demo",
                "version": "2026-05-01",
                "priorities": [{"priority": "P0", "fields": ["revenue"]}],
                "source_mappings": {
                    "revenue": {
                        "value_type": "money",
                        "statement_type": "income_statement",
                        "currency_requirement": "required",
                        "unit_requirement": "required",
                        "source_aliases": {
                            "akshare": ["营业收入"],
                            "yahoo": ["Total Revenue"],
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    catalog = load_source_mapping_catalog(path, priorities=("P0",))

    assert catalog.catalog_id == "demo"
    assert tuple(catalog.entries) == ("revenue",)
    assert catalog.entries["revenue"].source_aliases["akshare"] == ("营业收入",)
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_source_mapping_catalog.py -v`
Expected: FAIL because `catalog.py` does not exist.

- [x] **Step 3: Implement catalog loader**

Implement `SourceMappingCatalog` and `SourceMappingEntry` dataclasses plus `load_source_mapping_catalog(path, priorities)`.

- [x] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_source_mapping_catalog.py -v`
Expected: PASS.

### Task 3: Source Coverage Gate

**Files:**
- Create: `src/financial_report_llm_extractor/structured_sources/coverage.py`
- Test: `tests/test_source_coverage.py`

- [x] **Step 1: Write failing coverage tests**

```python
from decimal import Decimal

from financial_report_llm_extractor.structured_sources.catalog import SourceMappingEntry
from financial_report_llm_extractor.structured_sources.coverage import evaluate_source_coverage
from financial_report_llm_extractor.structured_sources.models import (
    SourceEvidence,
    SourceInventoryRecord,
)


def test_source_coverage_reports_present_and_missing_fields() -> None:
    entries = {
        "revenue": SourceMappingEntry(
            field_id="revenue",
            priority="P0",
            value_type="money",
            statement_type="income_statement",
            currency_requirement="required",
            unit_requirement="required",
            source_aliases={"akshare": ("营业收入",), "yahoo": ("Total Revenue",)},
        ),
        "net_profit": SourceMappingEntry(
            field_id="net_profit",
            priority="P0",
            value_type="money",
            statement_type="income_statement",
            currency_requirement="required",
            unit_requirement="required",
            source_aliases={"akshare": ("净利润",), "yahoo": ("Net Income",)},
        ),
    }
    records = [
        SourceInventoryRecord(
            source="akshare",
            market="CN",
            ticker="600519",
            statement_type="income_statement",
            period="2024-12-31",
            raw_field_name="营业收入",
            raw_value="100",
            parsed_numeric_value=Decimal("100"),
            currency="CNY",
            unit="yuan",
            source_evidence=(SourceEvidence("akshare", "akshare", "fn", "a1", "r1", "营业收入"),),
        )
    ]

    summary = evaluate_source_coverage(entries, records, required_sources=("akshare", "yahoo"))

    assert summary["total_fields"] == 2
    assert summary["combined"]["covered_fields"] == 1
    assert summary["combined"]["missing_fields"] == ["net_profit"]
    assert summary["by_source"]["akshare"]["covered_fields"] == 1
    assert summary["by_source"]["yahoo"]["covered_fields"] == 0
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_source_coverage.py -v`
Expected: FAIL because `coverage.py` does not exist.

- [x] **Step 3: Implement coverage evaluation**

Implement deterministic alias matching by source and raw field name. Block money candidates missing currency or unit.

- [x] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_source_coverage.py -v`
Expected: PASS.

### Task 4: Focused Verification

**Files:**
- Modify only as needed after Task 1-3.

- [x] **Step 1: Run source-first tests**

Run:

```bash
uv run pytest tests/test_structured_source_models.py tests/test_source_mapping_catalog.py tests/test_source_coverage.py -v
```

Expected: all tests pass.

- [x] **Step 2: Run existing core tests touched by catalog/coverage concepts**

Run:

```bash
uv run pytest tests/test_coverage_budget.py tests/test_money.py tests/test_models.py -v
```

Expected: all tests pass.

- [x] **Step 3: Run static checks if time permits**

Run:

```bash
uv run ruff check .
uv run mypy src tests
```

Expected: no lint or type errors.
