# Phase A Turtle Taxonomy, Coverage Matrix, And Minimal Mapping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Phase A as a Turtle-first metadata layer: full field taxonomy, planned coverage matrix, and a minimal source mapping contract linked to both.

**Architecture:** Add a small field metadata boundary outside provider adapters. `field_catalog/turtle_v015_field_taxonomy.json` defines all Turtle fields by domain and source mode; `field_catalog/turtle_v015_coverage_matrix.json` defines expected extraction routes; existing minimal source mapping is validated against both catalogs.

**Tech Stack:** Python 3.11 standard library, frozen dataclasses, JSON fixtures, pytest, existing `field_catalog/` and `structured_sources/catalog.py` patterns.

---

## Files

- Create: `src/financial_report_llm_extractor/field_metadata.py`
  - Owns taxonomy and coverage matrix dataclasses/loaders.
- Create: `field_catalog/turtle_v015_field_taxonomy.json`
  - Full Turtle v0.15 field taxonomy for every field in `turtle_v015_priority_fields.json`.
- Create: `field_catalog/turtle_v015_coverage_matrix.json`
  - Planned coverage route and verification status for every Turtle field.
- Modify: `field_catalog/turtle_v015_source_mapping_minimal.json`
  - Add references to taxonomy/coverage artifacts and per-entry domain/source-mode metadata.
- Modify: `src/financial_report_llm_extractor/structured_sources/catalog.py`
  - Load optional domain/source-mode/coverage metadata on minimal source mappings.
- Modify: `src/financial_report_llm_extractor/structured_sources/coverage.py`
  - Add summary helpers by domain, priority, source mode, and route.
- Create: `tests/test_field_metadata.py`
  - Unit tests for taxonomy and coverage matrix loaders.
- Modify: `tests/test_source_mapping_catalog.py`
  - Tests that minimal mapping agrees with taxonomy and coverage matrix.
- Modify: `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md`
  - Mark Phase A artifacts and validation commands after implementation.

## Task 1: A1 Taxonomy Loader Contracts

**Files:**
- Create: `src/financial_report_llm_extractor/field_metadata.py`
- Create: `tests/test_field_metadata.py`

- [ ] **Step 1: Write failing tests for taxonomy loading**

Add to `tests/test_field_metadata.py`:

```python
import json
from pathlib import Path

import pytest

from financial_report_llm_extractor.field_metadata import (
    load_field_taxonomy,
    validate_taxonomy_against_priority_catalog,
)


def test_load_field_taxonomy_reads_field_metadata(tmp_path: Path) -> None:
    taxonomy_path = tmp_path / "taxonomy.json"
    taxonomy_path.write_text(
        json.dumps(
            {
                "catalog_id": "demo_taxonomy",
                "version": "2026-05-02",
                "source_priority_catalog": "demo_priority",
                "fields": {
                    "revenue": {
                        "priority": "P0",
                        "domain": "income_statement",
                        "statement_type": "income_statement",
                        "value_type": "money",
                        "source_mode": "direct",
                        "period_type": "duration",
                        "scope_expectation": "consolidated",
                        "currency_requirement": "required",
                        "unit_requirement": "required",
                        "evidence_requirement": "source_only_allowed",
                        "fallback_policy": "pdf_allowed",
                        "description": "Revenue from contracts or operations.",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    taxonomy = load_field_taxonomy(taxonomy_path)

    assert taxonomy.catalog_id == "demo_taxonomy"
    assert taxonomy.fields["revenue"].domain == "income_statement"
    assert taxonomy.fields["revenue"].source_mode == "direct"


def test_taxonomy_validation_requires_exact_priority_catalog_coverage(
    tmp_path: Path,
) -> None:
    priority_path = tmp_path / "priority.json"
    priority_path.write_text(
        json.dumps(
            {
                "catalog_id": "priority",
                "version": "2026-05-02",
                "priorities": [
                    {"priority": "P0", "fields": ["revenue", "net_profit"]}
                ],
            }
        ),
        encoding="utf-8",
    )
    taxonomy_path = tmp_path / "taxonomy.json"
    taxonomy_path.write_text(
        json.dumps(
            {
                "catalog_id": "taxonomy",
                "version": "2026-05-02",
                "source_priority_catalog": "priority",
                "fields": {
                    "revenue": {
                        "priority": "P0",
                        "domain": "income_statement",
                        "statement_type": "income_statement",
                        "value_type": "money",
                        "source_mode": "direct",
                        "period_type": "duration",
                        "scope_expectation": "consolidated",
                        "currency_requirement": "required",
                        "unit_requirement": "required",
                        "evidence_requirement": "source_only_allowed",
                        "fallback_policy": "pdf_allowed",
                        "description": "Revenue.",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    taxonomy = load_field_taxonomy(taxonomy_path)

    with pytest.raises(ValueError, match="missing taxonomy fields"):
        validate_taxonomy_against_priority_catalog(taxonomy, priority_path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_field_metadata.py -v
```

Expected: FAIL with `ModuleNotFoundError` for `financial_report_llm_extractor.field_metadata`.

- [ ] **Step 3: Implement taxonomy dataclasses and loader**

Create `src/financial_report_llm_extractor/field_metadata.py` with:

```python
"""Turtle field taxonomy and planned coverage metadata."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


FieldDomain = Literal[
    "income_statement",
    "balance_sheet",
    "cash_flow",
    "shareholder_return",
    "accounting_adjustments",
    "notes_and_mda",
]
SourceMode = Literal["direct", "derived", "source_optional", "pdf_only", "llm_review"]
Requirement = Literal["required", "optional", "not_applicable"]
EvidenceRequirement = Literal[
    "source_only_allowed",
    "pdf_required",
    "llm_review_required",
]


@dataclass(frozen=True)
class FieldTaxonomyEntry:
    field_id: str
    priority: str
    domain: FieldDomain
    statement_type: str
    value_type: str
    source_mode: SourceMode
    period_type: str
    scope_expectation: str
    currency_requirement: Requirement
    unit_requirement: Requirement
    evidence_requirement: EvidenceRequirement
    fallback_policy: str
    description: str

    def validate(self) -> None:
        if not self.field_id:
            raise ValueError("field_id is required")
        if not self.priority:
            raise ValueError("priority is required")
        if not self.description:
            raise ValueError("description is required")
        if self.value_type == "money":
            if self.currency_requirement == "not_applicable":
                raise ValueError("money fields require currency metadata")
            if self.unit_requirement == "not_applicable":
                raise ValueError("money fields require unit metadata")


@dataclass(frozen=True)
class FieldTaxonomyCatalog:
    catalog_id: str
    version: str
    source_priority_catalog: str
    fields: dict[str, FieldTaxonomyEntry]

    def validate(self) -> None:
        if not self.catalog_id:
            raise ValueError("catalog_id is required")
        if not self.version:
            raise ValueError("version is required")
        if not self.source_priority_catalog:
            raise ValueError("source_priority_catalog is required")
        if not self.fields:
            raise ValueError("fields is required")
        for field_id, entry in self.fields.items():
            if field_id != entry.field_id:
                raise ValueError("taxonomy key must match field_id")
            entry.validate()


def load_field_taxonomy(path: Path) -> FieldTaxonomyCatalog:
    raw = json.loads(path.read_text(encoding="utf-8"))
    fields = {
        field_id: FieldTaxonomyEntry(field_id=field_id, **payload)
        for field_id, payload in raw.get("fields", {}).items()
    }
    catalog = FieldTaxonomyCatalog(
        catalog_id=str(raw.get("catalog_id", "")),
        version=str(raw.get("version", "")),
        source_priority_catalog=str(raw.get("source_priority_catalog", "")),
        fields=fields,
    )
    catalog.validate()
    return catalog


def load_priority_field_ids(path: Path) -> set[str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        str(field_id)
        for group in raw.get("priorities", [])
        for field_id in group.get("fields", [])
    }


def validate_taxonomy_against_priority_catalog(
    taxonomy: FieldTaxonomyCatalog,
    priority_catalog_path: Path,
) -> None:
    priority_fields = load_priority_field_ids(priority_catalog_path)
    taxonomy_fields = set(taxonomy.fields)
    missing = sorted(priority_fields - taxonomy_fields)
    extra = sorted(taxonomy_fields - priority_fields)
    if missing:
        raise ValueError(f"missing taxonomy fields: {missing}")
    if extra:
        raise ValueError(f"unknown taxonomy fields: {extra}")
```

- [ ] **Step 4: Run tests**

Run:

```bash
uv run pytest tests/test_field_metadata.py -v
```

Expected: PASS for the two taxonomy loader tests.

- [ ] **Step 5: Commit**

```bash
git add src/financial_report_llm_extractor/field_metadata.py tests/test_field_metadata.py
git commit -m "feat: add turtle field taxonomy loader"
```

## Task 2: A1 Full Taxonomy Fixture

**Files:**
- Create: `field_catalog/turtle_v015_field_taxonomy.json`
- Modify: `tests/test_field_metadata.py`

- [ ] **Step 1: Write failing tests for the real taxonomy fixture**

Append to `tests/test_field_metadata.py`:

```python
def test_real_turtle_taxonomy_covers_all_priority_fields() -> None:
    taxonomy = load_field_taxonomy(
        Path("field_catalog/turtle_v015_field_taxonomy.json")
    )

    validate_taxonomy_against_priority_catalog(
        taxonomy,
        Path("field_catalog/turtle_v015_priority_fields.json"),
    )

    assert taxonomy.fields["revenue"].domain == "income_statement"
    assert taxonomy.fields["total_assets"].domain == "balance_sheet"
    assert taxonomy.fields["operating_cash_flow"].domain == "cash_flow"
    assert taxonomy.fields["mda_risk_factors"].source_mode == "llm_review"


def test_real_turtle_taxonomy_supports_domain_queries() -> None:
    taxonomy = load_field_taxonomy(
        Path("field_catalog/turtle_v015_field_taxonomy.json")
    )

    p0_balance_sheet = sorted(
        entry.field_id
        for entry in taxonomy.fields.values()
        if entry.priority == "P0" and entry.domain == "balance_sheet"
    )

    assert "total_assets" in p0_balance_sheet
    assert "cash" in p0_balance_sheet
    assert "revenue" not in p0_balance_sheet
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_field_metadata.py::test_real_turtle_taxonomy_covers_all_priority_fields -v
```

Expected: FAIL with file-not-found for `field_catalog/turtle_v015_field_taxonomy.json`.

- [ ] **Step 3: Add the taxonomy fixture**

Create `field_catalog/turtle_v015_field_taxonomy.json`. Include every field currently listed in `field_catalog/turtle_v015_priority_fields.json`. Use Appendix A for the exact field classification table. Use this JSON shape:

```json
{
  "catalog_id": "turtle_v015_field_taxonomy",
  "version": "2026-05-02",
  "source_priority_catalog": "turtle_v015_priority_fields",
  "fields": {
    "revenue": {
      "priority": "P0",
      "domain": "income_statement",
      "statement_type": "income_statement",
      "value_type": "money",
      "source_mode": "direct",
      "period_type": "duration",
      "scope_expectation": "consolidated",
      "currency_requirement": "required",
      "unit_requirement": "required",
      "evidence_requirement": "source_only_allowed",
      "fallback_policy": "pdf_allowed",
      "description": "Revenue or operating revenue for the reporting period."
    },
    "total_assets": {
      "priority": "P0",
      "domain": "balance_sheet",
      "statement_type": "balance_sheet",
      "value_type": "money",
      "source_mode": "direct",
      "period_type": "point_in_time",
      "scope_expectation": "consolidated",
      "currency_requirement": "required",
      "unit_requirement": "required",
      "evidence_requirement": "source_only_allowed",
      "fallback_policy": "pdf_allowed",
      "description": "Total assets at the reporting date."
    },
    "operating_cash_flow": {
      "priority": "P0",
      "domain": "cash_flow",
      "statement_type": "cash_flow",
      "value_type": "money",
      "source_mode": "direct",
      "period_type": "duration",
      "scope_expectation": "consolidated",
      "currency_requirement": "required",
      "unit_requirement": "required",
      "evidence_requirement": "source_only_allowed",
      "fallback_policy": "pdf_allowed",
      "description": "Net cash generated from operating activities."
    },
    "mda_risk_factors": {
      "priority": "P4",
      "domain": "notes_and_mda",
      "statement_type": "mda",
      "value_type": "text",
      "source_mode": "llm_review",
      "period_type": "annual_text",
      "scope_expectation": "not_applicable",
      "currency_requirement": "not_applicable",
      "unit_requirement": "not_applicable",
      "evidence_requirement": "llm_review_required",
      "fallback_policy": "llm_review_required",
      "description": "Narrative risk factors from management discussion or annual-report text."
    }
  }
}
```

The snippet above shows the exact shape. Add every field listed in Appendix A using the exact metadata values from that table.

- [ ] **Step 4: Run tests**

Run:

```bash
uv run pytest tests/test_field_metadata.py -v
```

Expected: PASS for taxonomy fixture coverage.

- [ ] **Step 5: Commit**

```bash
git add field_catalog/turtle_v015_field_taxonomy.json tests/test_field_metadata.py
git commit -m "feat: add full turtle field taxonomy"
```

## Task 3: A2 Coverage Matrix Contracts

**Files:**
- Modify: `src/financial_report_llm_extractor/field_metadata.py`
- Modify: `tests/test_field_metadata.py`

- [ ] **Step 1: Write failing tests for coverage matrix loading**

Append to `tests/test_field_metadata.py`:

```python
from financial_report_llm_extractor.field_metadata import (
    load_coverage_matrix,
    validate_coverage_matrix_against_taxonomy,
)


def test_load_coverage_matrix_reads_routes(tmp_path: Path) -> None:
    path = tmp_path / "coverage.json"
    path.write_text(
        json.dumps(
            {
                "matrix_id": "demo_coverage",
                "version": "2026-05-02",
                "taxonomy_catalog": "demo_taxonomy",
                "fields": {
                    "revenue": {
                        "domain": "income_statement",
                        "priority": "P0",
                        "primary_route": "akshare_direct",
                        "verification": "verified",
                        "routes": [
                            {
                                "source": "akshare",
                                "mode": "direct",
                                "status": "verified",
                                "statement_type": "income_statement",
                                "evidence_requirement": "source_only_allowed",
                            }
                        ],
                        "notes": "Verified by captured AKShare fixture.",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    matrix = load_coverage_matrix(path)

    assert matrix.matrix_id == "demo_coverage"
    assert matrix.fields["revenue"].primary_route == "akshare_direct"
    assert matrix.fields["revenue"].verification == "verified"
    assert matrix.fields["revenue"].routes[0].status == "verified"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_field_metadata.py::test_load_coverage_matrix_reads_routes -v
```

Expected: FAIL with import error for `load_coverage_matrix`.

- [ ] **Step 3: Implement coverage matrix dataclasses and loader**

Add to `src/financial_report_llm_extractor/field_metadata.py`:

```python
PrimaryRoute = Literal[
    "akshare_direct",
    "yahoo_direct",
    "source_derived",
    "pdf_evidence",
    "llm_review",
    "unsupported_first_stage",
]
RouteSource = Literal["akshare", "yahoo", "pdf", "llm", "derived"]
RouteMode = Literal["direct", "derived", "evidence", "review", "unsupported"]
VerificationStatus = Literal["verified", "expected", "unknown", "unsupported"]


@dataclass(frozen=True)
class CoverageRoute:
    source: RouteSource
    mode: RouteMode
    status: VerificationStatus
    statement_type: str
    evidence_requirement: EvidenceRequirement

    def validate(self) -> None:
        if not self.source:
            raise ValueError("coverage route source is required")
        if not self.statement_type:
            raise ValueError("coverage route statement_type is required")


@dataclass(frozen=True)
class CoverageMatrixEntry:
    field_id: str
    domain: FieldDomain
    priority: str
    primary_route: PrimaryRoute
    verification: VerificationStatus
    routes: tuple[CoverageRoute, ...]
    notes: str = ""

    def validate(self) -> None:
        if not self.field_id:
            raise ValueError("field_id is required")
        if not self.priority:
            raise ValueError("priority is required")
        if not self.routes:
            raise ValueError("coverage routes are required")
        for route in self.routes:
            route.validate()


@dataclass(frozen=True)
class CoverageMatrix:
    matrix_id: str
    version: str
    taxonomy_catalog: str
    fields: dict[str, CoverageMatrixEntry]

    def validate(self) -> None:
        if not self.matrix_id:
            raise ValueError("matrix_id is required")
        if not self.version:
            raise ValueError("version is required")
        if not self.taxonomy_catalog:
            raise ValueError("taxonomy_catalog is required")
        if not self.fields:
            raise ValueError("coverage fields are required")
        for field_id, entry in self.fields.items():
            if field_id != entry.field_id:
                raise ValueError("coverage key must match field_id")
            entry.validate()


def load_coverage_matrix(path: Path) -> CoverageMatrix:
    raw = json.loads(path.read_text(encoding="utf-8"))
    fields: dict[str, CoverageMatrixEntry] = {}
    for field_id, payload in raw.get("fields", {}).items():
        routes = tuple(CoverageRoute(**route) for route in payload.get("routes", []))
        fields[field_id] = CoverageMatrixEntry(
            field_id=field_id,
            domain=payload["domain"],
            priority=payload["priority"],
            primary_route=payload["primary_route"],
            verification=payload["verification"],
            routes=routes,
            notes=str(payload.get("notes", "")),
        )
    matrix = CoverageMatrix(
        matrix_id=str(raw.get("matrix_id", "")),
        version=str(raw.get("version", "")),
        taxonomy_catalog=str(raw.get("taxonomy_catalog", "")),
        fields=fields,
    )
    matrix.validate()
    return matrix


def validate_coverage_matrix_against_taxonomy(
    matrix: CoverageMatrix,
    taxonomy: FieldTaxonomyCatalog,
) -> None:
    matrix_fields = set(matrix.fields)
    taxonomy_fields = set(taxonomy.fields)
    missing = sorted(taxonomy_fields - matrix_fields)
    extra = sorted(matrix_fields - taxonomy_fields)
    if missing:
        raise ValueError(f"missing coverage fields: {missing}")
    if extra:
        raise ValueError(f"unknown coverage fields: {extra}")
    for field_id, entry in matrix.fields.items():
        taxonomy_entry = taxonomy.fields[field_id]
        if entry.domain != taxonomy_entry.domain:
            raise ValueError(f"{field_id} coverage domain does not match taxonomy")
        if entry.priority != taxonomy_entry.priority:
            raise ValueError(f"{field_id} coverage priority does not match taxonomy")
        if taxonomy_entry.source_mode in {"pdf_only", "llm_review"}:
            if entry.primary_route not in {"pdf_evidence", "llm_review"}:
                raise ValueError(f"{field_id} source mode requires PDF or LLM route")
        if not _primary_route_has_matching_route(entry):
            raise ValueError(f"{field_id} primary_route has no matching route")
        if entry.verification == "verified" and not _primary_route_is_verified(entry):
            raise ValueError(f"{field_id} verified field requires verified primary route")


def _primary_route_has_matching_route(entry: CoverageMatrixEntry) -> bool:
    expected = {
        "akshare_direct": ("akshare", "direct"),
        "yahoo_direct": ("yahoo", "direct"),
        "source_derived": ("derived", "derived"),
        "pdf_evidence": ("pdf", "evidence"),
        "llm_review": ("llm", "review"),
        "unsupported_first_stage": ("derived", "unsupported"),
    }[entry.primary_route]
    return any(
        route.source == expected[0] and route.mode == expected[1]
        for route in entry.routes
    )


def _primary_route_is_verified(entry: CoverageMatrixEntry) -> bool:
    expected = {
        "akshare_direct": ("akshare", "direct"),
        "yahoo_direct": ("yahoo", "direct"),
        "source_derived": ("derived", "derived"),
        "pdf_evidence": ("pdf", "evidence"),
        "llm_review": ("llm", "review"),
        "unsupported_first_stage": ("derived", "unsupported"),
    }[entry.primary_route]
    return any(
        route.source == expected[0]
        and route.mode == expected[1]
        and route.status == "verified"
        for route in entry.routes
    )
```

- [ ] **Step 4: Run tests**

Run:

```bash
uv run pytest tests/test_field_metadata.py -v
```

Expected: PASS for coverage matrix loader tests.

- [ ] **Step 5: Commit**

```bash
git add src/financial_report_llm_extractor/field_metadata.py tests/test_field_metadata.py
git commit -m "feat: add turtle coverage matrix loader"
```

## Task 4: A2 Full Coverage Matrix Fixture And Summaries

**Files:**
- Create: `field_catalog/turtle_v015_coverage_matrix.json`
- Modify: `tests/test_field_metadata.py`
- Modify: `src/financial_report_llm_extractor/field_metadata.py`

- [ ] **Step 1: Write failing tests for the real coverage matrix**

Append to `tests/test_field_metadata.py`:

```python
def test_real_coverage_matrix_covers_taxonomy_fields() -> None:
    taxonomy = load_field_taxonomy(
        Path("field_catalog/turtle_v015_field_taxonomy.json")
    )
    matrix = load_coverage_matrix(
        Path("field_catalog/turtle_v015_coverage_matrix.json")
    )

    validate_coverage_matrix_against_taxonomy(matrix, taxonomy)

    assert matrix.fields["revenue"].primary_route == "akshare_direct"
    assert matrix.fields["gross_profit"].primary_route in {
        "akshare_direct",
        "yahoo_direct",
    }
    assert matrix.fields["mda_business_review"].primary_route == "llm_review"


def test_coverage_matrix_can_summarize_by_domain_and_route() -> None:
    matrix = load_coverage_matrix(
        Path("field_catalog/turtle_v015_coverage_matrix.json")
    )

    summary = summarize_coverage_matrix(matrix)

    assert summary["total_fields"] == len(matrix.fields)
    assert summary["by_domain"]["income_statement"] >= 1
    assert summary["by_primary_route"]["llm_review"] >= 1
```

Update the imports in `tests/test_field_metadata.py` to include `summarize_coverage_matrix`.

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_field_metadata.py::test_real_coverage_matrix_covers_taxonomy_fields -v
```

Expected: FAIL with file-not-found for `field_catalog/turtle_v015_coverage_matrix.json`.

- [ ] **Step 3: Add summary helper**

Add to `src/financial_report_llm_extractor/field_metadata.py`:

```python
def summarize_coverage_matrix(matrix: CoverageMatrix) -> dict[str, object]:
    by_domain: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    by_primary_route: dict[str, int] = {}
    for entry in matrix.fields.values():
        by_domain[entry.domain] = by_domain.get(entry.domain, 0) + 1
        by_priority[entry.priority] = by_priority.get(entry.priority, 0) + 1
        by_primary_route[entry.primary_route] = (
            by_primary_route.get(entry.primary_route, 0) + 1
        )
    return {
        "total_fields": len(matrix.fields),
        "by_domain": dict(sorted(by_domain.items())),
        "by_priority": dict(sorted(by_priority.items())),
        "by_primary_route": dict(sorted(by_primary_route.items())),
    }
```

- [ ] **Step 4: Add the coverage matrix fixture**

Create `field_catalog/turtle_v015_coverage_matrix.json`. Include every taxonomy field. Use Appendix B for the exact `primary_route` and provider status. Use this shape:

```json
{
  "matrix_id": "turtle_v015_coverage_matrix",
  "version": "2026-05-02",
  "taxonomy_catalog": "turtle_v015_field_taxonomy",
  "fields": {
    "revenue": {
      "domain": "income_statement",
      "priority": "P0",
      "primary_route": "akshare_direct",
      "verification": "verified",
      "routes": [
        {
          "source": "akshare",
          "mode": "direct",
          "status": "verified",
          "statement_type": "income_statement",
          "evidence_requirement": "source_only_allowed"
        },
        {
          "source": "yahoo",
          "mode": "direct",
          "status": "verified",
          "statement_type": "income_statement",
          "evidence_requirement": "source_only_allowed"
        }
      ],
      "notes": "Verified by AKShare 600519 and Yahoo 0001.HK captured income statement fixtures."
    },
    "mda_business_review": {
      "domain": "notes_and_mda",
      "priority": "P4",
      "primary_route": "llm_review",
      "verification": "expected",
      "routes": [
        {
          "source": "llm",
          "mode": "review",
          "status": "expected",
          "statement_type": "mda",
          "evidence_requirement": "llm_review_required"
        }
      ],
      "notes": "Narrative field requiring selected PDF evidence and LLM review."
    }
  }
}
```

Add every field listed in Appendix B. For fields marked `verified`, add a note pointing to the captured fixture that supports it. For fields marked `expected` or `unknown`, state that no captured provider proof exists yet.

- [ ] **Step 5: Run tests**

Run:

```bash
uv run pytest tests/test_field_metadata.py -v
```

Expected: PASS for taxonomy and coverage matrix fixtures.

- [ ] **Step 6: Commit**

```bash
git add field_catalog/turtle_v015_coverage_matrix.json src/financial_report_llm_extractor/field_metadata.py tests/test_field_metadata.py
git commit -m "feat: add turtle coverage matrix"
```

## Task 5: A3 Link Minimal Source Mapping To Taxonomy And Coverage

**Files:**
- Modify: `field_catalog/turtle_v015_source_mapping_minimal.json`
- Modify: `src/financial_report_llm_extractor/structured_sources/catalog.py`
- Modify: `tests/test_source_mapping_catalog.py`

- [ ] **Step 1: Write failing tests for mapping metadata**

Append to `tests/test_source_mapping_catalog.py`:

```python
from financial_report_llm_extractor.field_metadata import (
    load_coverage_matrix,
    load_field_taxonomy,
)


def test_minimal_source_mapping_references_taxonomy_and_coverage() -> None:
    taxonomy = load_field_taxonomy(
        Path("field_catalog/turtle_v015_field_taxonomy.json")
    )
    coverage = load_coverage_matrix(
        Path("field_catalog/turtle_v015_coverage_matrix.json")
    )
    catalog = load_source_mapping_catalog(
        Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        priorities=("P0", "P1"),
    )

    revenue = catalog.entries["revenue"]

    assert revenue.domain == taxonomy.fields["revenue"].domain
    assert revenue.source_mode == taxonomy.fields["revenue"].source_mode
    assert revenue.primary_route == coverage.fields["revenue"].primary_route
    assert revenue.verification_status in {"verified", "expected", "unknown"}


def test_minimal_source_mapping_entries_match_taxonomy_and_coverage() -> None:
    taxonomy = load_field_taxonomy(
        Path("field_catalog/turtle_v015_field_taxonomy.json")
    )
    coverage = load_coverage_matrix(
        Path("field_catalog/turtle_v015_coverage_matrix.json")
    )
    catalog = load_source_mapping_catalog(
        Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        priorities=("P0", "P1"),
    )

    for field_id, entry in catalog.entries.items():
        taxonomy_entry = taxonomy.fields[field_id]
        coverage_entry = coverage.fields[field_id]
        assert entry.domain == taxonomy_entry.domain
        assert entry.source_mode == taxonomy_entry.source_mode
        assert entry.primary_route == coverage_entry.primary_route
        assert entry.verification_status == coverage_entry.verification
        if taxonomy_entry.statement_type != "mixed":
            assert entry.statement_type == taxonomy_entry.statement_type
        assert entry.source_mode not in {"pdf_only", "llm_review"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_source_mapping_catalog.py::test_minimal_source_mapping_references_taxonomy_and_coverage -v
```

Expected: FAIL because `SourceMappingEntry` has no `domain`, `source_mode`, `primary_route`, or `verification_status`.

- [ ] **Step 3: Extend source mapping dataclass**

Modify `SourceMappingEntry` in `src/financial_report_llm_extractor/structured_sources/catalog.py`:

```python
@dataclass(frozen=True)
class SourceMappingEntry:
    field_id: str
    priority: str
    value_type: SourceValueType
    statement_type: str
    currency_requirement: Requirement
    unit_requirement: Requirement
    source_aliases: dict[str, tuple[str, ...]]
    domain: str = "unknown"
    source_mode: str = "direct"
    primary_route: str = "akshare_direct"
    verification_status: str = "unknown"
    period_expectation: str = "annual"
    scope_expectation: str = "unknown"
    pdf_aliases: tuple[str, ...] = field(default_factory=tuple)
    derivation: str | None = None
    fallback_policy: str = "pdf_allowed"
```

In `load_source_mapping_catalog()`, pass the new optional fields:

```python
entry = SourceMappingEntry(
    field_id=field_id,
    priority=priority,
    value_type=mapping.get("value_type", "money"),
    statement_type=mapping.get("statement_type", "unknown"),
    currency_requirement=mapping.get("currency_requirement", "required"),
    unit_requirement=mapping.get("unit_requirement", "required"),
    source_aliases=aliases,
    domain=mapping.get("domain", "unknown"),
    source_mode=mapping.get("source_mode", "direct"),
    primary_route=mapping.get("primary_route", "akshare_direct"),
    verification_status=mapping.get("verification_status", "unknown"),
    period_expectation=mapping.get("period_expectation", "annual"),
    scope_expectation=mapping.get("scope_expectation", "unknown"),
    pdf_aliases=tuple(str(alias) for alias in mapping.get("pdf_aliases", [])),
    derivation=mapping.get("derivation"),
    fallback_policy=mapping.get("fallback_policy", "pdf_allowed"),
)
```

- [ ] **Step 4: Update minimal source mapping fixture**

In `field_catalog/turtle_v015_source_mapping_minimal.json`, add top-level references:

```json
"taxonomy_catalog": "turtle_v015_field_taxonomy",
"coverage_matrix": "turtle_v015_coverage_matrix"
```

For each entry in `source_mappings`, add:

```json
"domain": "income_statement",
"source_mode": "direct",
"primary_route": "akshare_direct",
"verification_status": "verified"
```

Use the domain and route from Appendix A and Appendix B. For `gross_profit`, use `domain: "income_statement"`, `source_mode: "direct"`, `primary_route: "yahoo_direct"`, and `verification_status: "verified"` because the Yahoo `0001.HK` captured income statement fixture verifies it.

- [ ] **Step 5: Run tests**

Run:

```bash
uv run pytest tests/test_source_mapping_catalog.py tests/test_field_metadata.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add field_catalog/turtle_v015_source_mapping_minimal.json src/financial_report_llm_extractor/structured_sources/catalog.py tests/test_source_mapping_catalog.py
git commit -m "feat: link minimal source mapping to turtle taxonomy"
```

## Task 6: Domain And Route Coverage Reporting

**Files:**
- Modify: `src/financial_report_llm_extractor/structured_sources/coverage.py`
- Modify: `tests/test_source_coverage.py`

- [ ] **Step 1: Write failing test for taxonomy-aware coverage summary**

Append to `tests/test_source_coverage.py`:

```python
from financial_report_llm_extractor.structured_sources.coverage import (
    summarize_source_coverage_by_metadata,
)


def test_source_coverage_summary_groups_by_domain_and_route() -> None:
    entries = {
        "revenue": SourceMappingEntry(
            field_id="revenue",
            priority="P0",
            value_type="money",
            statement_type="income_statement",
            currency_requirement="required",
            unit_requirement="required",
            source_aliases={"akshare": ("营业收入",)},
            domain="income_statement",
            source_mode="direct",
            primary_route="akshare_direct",
            verification_status="verified",
        )
    }

    summary = summarize_source_coverage_by_metadata(entries)

    assert summary["total_fields"] == 1
    assert summary["by_domain"] == {"income_statement": 1}
    assert summary["by_priority"] == {"P0": 1}
    assert summary["by_primary_route"] == {"akshare_direct": 1}
```

Ensure `SourceMappingEntry` is imported in the test file if it is not already present.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_source_coverage.py::test_source_coverage_summary_groups_by_domain_and_route -v
```

Expected: FAIL with import error for `summarize_source_coverage_by_metadata`.

- [ ] **Step 3: Implement metadata summary helper**

Add to `src/financial_report_llm_extractor/structured_sources/coverage.py`:

```python
def summarize_source_coverage_by_metadata(
    entries: Mapping[str, SourceMappingEntry],
) -> dict[str, object]:
    by_domain: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    by_source_mode: dict[str, int] = {}
    by_primary_route: dict[str, int] = {}
    for entry in entries.values():
        by_domain[entry.domain] = by_domain.get(entry.domain, 0) + 1
        by_priority[entry.priority] = by_priority.get(entry.priority, 0) + 1
        by_source_mode[entry.source_mode] = by_source_mode.get(entry.source_mode, 0) + 1
        by_primary_route[entry.primary_route] = (
            by_primary_route.get(entry.primary_route, 0) + 1
        )
    return {
        "total_fields": len(entries),
        "by_domain": dict(sorted(by_domain.items())),
        "by_priority": dict(sorted(by_priority.items())),
        "by_source_mode": dict(sorted(by_source_mode.items())),
        "by_primary_route": dict(sorted(by_primary_route.items())),
    }
```

- [ ] **Step 4: Run tests**

Run:

```bash
uv run pytest tests/test_source_coverage.py tests/test_source_mapping_catalog.py tests/test_field_metadata.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/financial_report_llm_extractor/structured_sources/coverage.py tests/test_source_coverage.py
git commit -m "feat: summarize source coverage by turtle metadata"
```

## Task 7: Documentation And Verification

**Files:**
- Modify: `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md`
- Modify: `docs/2026-04-30-codex-claude-handoff-prompt.md`

- [ ] **Step 1: Update roadmap status**

In `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md`, under Phase A1/A2/A3, add implementation notes for the created artifacts:

```markdown
Implementation note:

- `field_catalog/turtle_v015_field_taxonomy.json` contains full Turtle field taxonomy.
- `field_catalog/turtle_v015_coverage_matrix.json` contains expected coverage route by field.
- `field_catalog/turtle_v015_source_mapping_minimal.json` is linked to taxonomy and coverage metadata.
```

- [ ] **Step 2: Update handoff**

In `docs/2026-04-30-codex-claude-handoff-prompt.md`, add the two new artifacts to the source-first foundation section:

```markdown
- `field_catalog/turtle_v015_field_taxonomy.json` classifies every Turtle field by domain and source mode.
- `field_catalog/turtle_v015_coverage_matrix.json` records planned coverage routes and verification status.
```

- [ ] **Step 3: Run focused verification**

Run:

```bash
uv run pytest tests/test_field_metadata.py tests/test_source_mapping_catalog.py tests/test_source_coverage.py -v
uv run ruff check src/financial_report_llm_extractor/field_metadata.py src/financial_report_llm_extractor/structured_sources/catalog.py src/financial_report_llm_extractor/structured_sources/coverage.py tests/test_field_metadata.py tests/test_source_mapping_catalog.py tests/test_source_coverage.py
uv run mypy src tests
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 4: Run full verification**

Run:

```bash
uv run pytest -v
uv run ruff check .
uv run mypy src tests
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 5: Commit**

```bash
git add docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md docs/2026-04-30-codex-claude-handoff-prompt.md
git commit -m "docs: document phase a field metadata artifacts"
```

## Self-Review

- Spec coverage: A1 taxonomy, A2 coverage matrix, and A3 minimal source mapping linkage are covered by Tasks 1-6.
- Provider scope: no task calls real AKShare/Yahoo; captured validation remains a Phase C/D/E input.
- Validation: every new artifact has tests for exact field coverage and consistency.
- Integration: existing minimal source mapping is extended without changing provider adapter behavior.

## Appendix A: Field Taxonomy Table

Use these values for `field_catalog/turtle_v015_field_taxonomy.json`.

| field_id | priority | domain | statement_type | value_type | source_mode | period_type | scope_expectation | currency_requirement | unit_requirement | evidence_requirement | fallback_policy |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| revenue | P0 | income_statement | income_statement | money | direct | duration | consolidated | required | required | source_only_allowed | pdf_allowed |
| operating_cost | P0 | income_statement | income_statement | money | direct | duration | consolidated | required | required | source_only_allowed | pdf_allowed |
| operating_profit | P0 | income_statement | income_statement | money | direct | duration | consolidated | required | required | source_only_allowed | pdf_allowed |
| net_profit | P0 | income_statement | income_statement | money | direct | duration | consolidated | required | required | source_only_allowed | pdf_allowed |
| total_assets | P0 | balance_sheet | balance_sheet | money | direct | point_in_time | consolidated | required | required | source_only_allowed | pdf_allowed |
| total_liabilities | P0 | balance_sheet | balance_sheet | money | direct | point_in_time | consolidated | required | required | source_only_allowed | pdf_allowed |
| equity_attributable_to_owners | P0 | balance_sheet | balance_sheet | money | direct | point_in_time | attributable_to_owners | required | required | source_only_allowed | pdf_allowed |
| operating_cash_flow | P0 | cash_flow | cash_flow | money | direct | duration | consolidated | required | required | source_only_allowed | pdf_allowed |
| investing_cash_flow | P0 | cash_flow | cash_flow | money | direct | duration | consolidated | required | required | source_only_allowed | pdf_allowed |
| financing_cash_flow | P0 | cash_flow | cash_flow | money | direct | duration | consolidated | required | required | source_only_allowed | pdf_allowed |
| cash | P0 | balance_sheet | balance_sheet | money | direct | point_in_time | consolidated | required | required | source_only_allowed | pdf_allowed |
| money_cap | P0 | balance_sheet | balance_sheet | money | direct | point_in_time | consolidated | required | required | source_only_allowed | pdf_allowed |
| st_borr | P0 | balance_sheet | balance_sheet | money | direct | point_in_time | consolidated | required | required | source_only_allowed | pdf_allowed |
| lt_borr | P0 | balance_sheet | balance_sheet | money | direct | point_in_time | consolidated | required | required | source_only_allowed | pdf_allowed |
| bond_payable | P0 | balance_sheet | balance_sheet | money | direct | point_in_time | consolidated | required | required | source_only_allowed | pdf_allowed |
| accounts_receiv | P0 | balance_sheet | balance_sheet | money | direct | point_in_time | consolidated | required | required | source_only_allowed | pdf_allowed |
| acct_payable | P0 | balance_sheet | balance_sheet | money | direct | point_in_time | consolidated | required | required | source_only_allowed | pdf_allowed |
| inventories | P0 | balance_sheet | balance_sheet | money | direct | point_in_time | consolidated | required | required | source_only_allowed | pdf_allowed |
| fix_assets | P0 | balance_sheet | balance_sheet | money | direct | point_in_time | consolidated | required | required | source_only_allowed | pdf_allowed |
| cip | P0 | balance_sheet | balance_sheet | money | direct | point_in_time | consolidated | required | required | source_only_allowed | pdf_allowed |
| rd_exp | P0 | income_statement | income_statement | money | source_optional | duration | consolidated | required | required | pdf_required | pdf_allowed |
| invest_income | P0 | income_statement | income_statement | money | direct | duration | consolidated | required | required | source_only_allowed | pdf_allowed |
| gross_profit | P1 | income_statement | income_statement | money | direct | duration | consolidated | required | required | source_only_allowed | pdf_allowed |
| selling_general_administrative | P1 | income_statement | income_statement | money | direct | duration | consolidated | required | required | source_only_allowed | pdf_allowed |
| fv_value_chg_gain | P1 | income_statement | income_statement | money | source_optional | duration | consolidated | required | required | pdf_required | pdf_allowed |
| non_oper_income | P1 | income_statement | income_statement | money | direct | duration | consolidated | required | required | source_only_allowed | pdf_allowed |
| non_oper_exp | P1 | income_statement | income_statement | money | direct | duration | consolidated | required | required | source_only_allowed | pdf_allowed |
| total_cur_assets | P1 | balance_sheet | balance_sheet | money | direct | point_in_time | consolidated | required | required | source_only_allowed | pdf_allowed |
| other_cur_assets | P1 | balance_sheet | balance_sheet | money | source_optional | point_in_time | consolidated | required | required | pdf_required | pdf_allowed |
| total_cur_liab | P1 | balance_sheet | balance_sheet | money | direct | point_in_time | consolidated | required | required | source_only_allowed | pdf_allowed |
| defer_tax_assets | P1 | balance_sheet | balance_sheet | money | direct | point_in_time | consolidated | required | required | source_only_allowed | pdf_allowed |
| defer_tax_liab | P1 | balance_sheet | balance_sheet | money | direct | point_in_time | consolidated | required | required | source_only_allowed | pdf_allowed |
| minority_int | P1 | balance_sheet | balance_sheet | money | direct | point_in_time | consolidated | required | required | source_only_allowed | pdf_allowed |
| stock_based_compensation | P2 | cash_flow | cash_flow | money | source_optional | duration | consolidated | required | required | pdf_required | pdf_allowed |
| change_in_receivables | P2 | cash_flow | cash_flow | money | source_optional | duration | consolidated | required | required | pdf_required | pdf_allowed |
| change_in_payables | P2 | cash_flow | cash_flow | money | source_optional | duration | consolidated | required | required | pdf_required | pdf_allowed |
| change_in_inventory | P2 | cash_flow | cash_flow | money | source_optional | duration | consolidated | required | required | pdf_required | pdf_allowed |
| receiv_tax_refund | P2 | cash_flow | cash_flow | money | source_optional | duration | consolidated | required | required | pdf_required | pdf_allowed |
| repurchase_of_stock | P2 | shareholder_return | cash_flow | money | source_optional | duration | consolidated | required | required | pdf_required | pdf_allowed |
| dividends_paid | P2 | shareholder_return | cash_flow | money | source_optional | duration | consolidated | required | required | pdf_required | pdf_allowed |
| capital_expenditures | P2 | cash_flow | cash_flow | money | source_optional | duration | consolidated | required | required | pdf_required | pdf_allowed |
| depreciation_amortization | P2 | accounting_adjustments | cash_flow | money | source_optional | duration | consolidated | required | required | pdf_required | pdf_allowed |
| dps | P3 | shareholder_return | announcement | money | source_optional | event | consolidated | required | required | pdf_required | pdf_allowed |
| dividend_plan | P3 | shareholder_return | announcement | text | pdf_only | event | not_applicable | not_applicable | not_applicable | pdf_required | pdf_allowed |
| buyback_cancellation_progress | P3 | shareholder_return | announcement | text | pdf_only | event | not_applicable | not_applicable | not_applicable | pdf_required | pdf_allowed |
| capitalized_rd | P3 | accounting_adjustments | notes | money | pdf_only | duration | consolidated | required | required | pdf_required | pdf_allowed |
| capitalized_interest | P3 | accounting_adjustments | notes | money | pdf_only | duration | consolidated | required | required | pdf_required | pdf_allowed |
| receivables_aging | P3 | notes_and_mda | notes | text | pdf_only | point_in_time | consolidated | not_applicable | not_applicable | pdf_required | pdf_allowed |
| bad_debt_provision | P3 | notes_and_mda | notes | money | pdf_only | point_in_time | consolidated | required | required | pdf_required | pdf_allowed |
| related_party_receivables_payables | P3 | notes_and_mda | notes | text | pdf_only | point_in_time | consolidated | not_applicable | not_applicable | pdf_required | pdf_allowed |
| contingent_liabilities_commitments | P3 | notes_and_mda | notes | text | pdf_only | point_in_time | consolidated | not_applicable | not_applicable | pdf_required | pdf_allowed |
| lease_liability_maturity | P3 | notes_and_mda | notes | text | pdf_only | point_in_time | consolidated | not_applicable | not_applicable | pdf_required | pdf_allowed |
| segment_revenue_profit | P3 | notes_and_mda | notes | text | pdf_only | duration | consolidated | not_applicable | not_applicable | pdf_required | pdf_allowed |
| restricted_cash | P3 | notes_and_mda | notes | money | pdf_only | point_in_time | consolidated | required | required | pdf_required | pdf_allowed |
| time_deposits_or_wealth_products | P3 | notes_and_mda | notes | money | pdf_only | point_in_time | consolidated | required | required | pdf_required | pdf_allowed |
| interest_paid_cash | P3 | cash_flow | cash_flow | money | source_optional | duration | consolidated | required | required | pdf_required | pdf_allowed |
| mda_business_review | P4 | notes_and_mda | mda | text | llm_review | annual_text | not_applicable | not_applicable | not_applicable | llm_review_required | llm_review_required |
| mda_forward_guidance | P4 | notes_and_mda | mda | text | llm_review | annual_text | not_applicable | not_applicable | not_applicable | llm_review_required | llm_review_required |
| mda_risk_factors | P4 | notes_and_mda | mda | text | llm_review | annual_text | not_applicable | not_applicable | not_applicable | llm_review_required | llm_review_required |
| dividend_policy_text | P4 | notes_and_mda | notes | text | llm_review | annual_text | not_applicable | not_applicable | not_applicable | llm_review_required | llm_review_required |
| audit_opinion | P4 | notes_and_mda | notes | text | llm_review | annual_text | not_applicable | not_applicable | not_applicable | llm_review_required | llm_review_required |
| auditor_change_history | P4 | notes_and_mda | notes | text | llm_review | annual_text | not_applicable | not_applicable | not_applicable | llm_review_required | llm_review_required |

## Appendix B: Coverage Route Table

Use these values for `field_catalog/turtle_v015_coverage_matrix.json`.

| field_id | primary_route | primary_source | primary_mode | verification |
| --- | --- | --- | --- | --- |
| revenue | akshare_direct | akshare | direct | verified |
| operating_cost | akshare_direct | akshare | direct | expected |
| operating_profit | akshare_direct | akshare | direct | expected |
| net_profit | akshare_direct | akshare | direct | verified |
| total_assets | akshare_direct | akshare | direct | verified |
| total_liabilities | akshare_direct | akshare | direct | verified |
| equity_attributable_to_owners | akshare_direct | akshare | direct | expected |
| operating_cash_flow | akshare_direct | akshare | direct | verified |
| investing_cash_flow | akshare_direct | akshare | direct | expected |
| financing_cash_flow | akshare_direct | akshare | direct | expected |
| cash | akshare_direct | akshare | direct | verified |
| money_cap | akshare_direct | akshare | direct | expected |
| st_borr | akshare_direct | akshare | direct | expected |
| lt_borr | akshare_direct | akshare | direct | expected |
| bond_payable | akshare_direct | akshare | direct | expected |
| accounts_receiv | akshare_direct | akshare | direct | expected |
| acct_payable | akshare_direct | akshare | direct | expected |
| inventories | akshare_direct | akshare | direct | expected |
| fix_assets | akshare_direct | akshare | direct | expected |
| cip | akshare_direct | akshare | direct | expected |
| rd_exp | akshare_direct | akshare | direct | expected |
| invest_income | akshare_direct | akshare | direct | expected |
| gross_profit | yahoo_direct | yahoo | direct | verified |
| selling_general_administrative | yahoo_direct | yahoo | direct | expected |
| fv_value_chg_gain | akshare_direct | akshare | direct | expected |
| non_oper_income | akshare_direct | akshare | direct | expected |
| non_oper_exp | akshare_direct | akshare | direct | expected |
| total_cur_assets | akshare_direct | akshare | direct | verified |
| other_cur_assets | akshare_direct | akshare | direct | expected |
| total_cur_liab | akshare_direct | akshare | direct | verified |
| defer_tax_assets | akshare_direct | akshare | direct | expected |
| defer_tax_liab | akshare_direct | akshare | direct | expected |
| minority_int | akshare_direct | akshare | direct | expected |
| stock_based_compensation | yahoo_direct | yahoo | direct | expected |
| change_in_receivables | yahoo_direct | yahoo | direct | expected |
| change_in_payables | yahoo_direct | yahoo | direct | expected |
| change_in_inventory | yahoo_direct | yahoo | direct | expected |
| receiv_tax_refund | akshare_direct | akshare | direct | expected |
| repurchase_of_stock | yahoo_direct | yahoo | direct | expected |
| dividends_paid | akshare_direct | akshare | direct | expected |
| capital_expenditures | yahoo_direct | yahoo | direct | expected |
| depreciation_amortization | yahoo_direct | yahoo | direct | expected |
| dps | pdf_evidence | pdf | evidence | expected |
| dividend_plan | pdf_evidence | pdf | evidence | expected |
| buyback_cancellation_progress | pdf_evidence | pdf | evidence | expected |
| capitalized_rd | pdf_evidence | pdf | evidence | expected |
| capitalized_interest | pdf_evidence | pdf | evidence | expected |
| receivables_aging | pdf_evidence | pdf | evidence | expected |
| bad_debt_provision | pdf_evidence | pdf | evidence | expected |
| related_party_receivables_payables | pdf_evidence | pdf | evidence | expected |
| contingent_liabilities_commitments | pdf_evidence | pdf | evidence | expected |
| lease_liability_maturity | pdf_evidence | pdf | evidence | expected |
| segment_revenue_profit | pdf_evidence | pdf | evidence | expected |
| restricted_cash | pdf_evidence | pdf | evidence | expected |
| time_deposits_or_wealth_products | pdf_evidence | pdf | evidence | expected |
| interest_paid_cash | akshare_direct | akshare | direct | expected |
| mda_business_review | llm_review | llm | review | expected |
| mda_forward_guidance | llm_review | llm | review | expected |
| mda_risk_factors | llm_review | llm | review | expected |
| dividend_policy_text | llm_review | llm | review | expected |
| audit_opinion | llm_review | llm | review | expected |
| auditor_change_history | llm_review | llm | review | expected |
