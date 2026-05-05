# Source Policy Conflict Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic source policy and conflict classification so provider disagreements are explained, policy-selected primary values remain reviewable, and combined coverage is no longer reduced solely by cross-check source disagreement.

**Architecture:** Extend the source mapping catalog with additive policy metadata, add a focused `source_policy.py` module that classifies conflicts and resolves selected candidates, then thread the result into source-first export and provider baseline replay summaries. Reconciliation remains conservative; policy resolution is an explicit post-reconciliation layer that preserves all source evidence and review requirements.

**Tech Stack:** Python 3.11 standard library, frozen dataclasses, existing source catalog/mapping/reconciliation/export pipeline, checked-in provider baseline fixture, `pytest`, `ruff`, `mypy`.

---

## File Structure

- Modify: `src/financial_report_llm_extractor/structured_sources/catalog.py`
  - Add `SourcePolicy`, `SourceSemanticVariants`, and `MarketSourcePolicy` dataclasses.
  - Parse optional `source_policy` from source mapping JSON.
- Modify: `field_catalog/turtle_v015_source_mapping_minimal.json`
  - Add source policy metadata for `revenue`, `net_profit`, HK balance-sheet totals, `gross_profit`, and Yahoo-only HK fields.
  - Reorder `net_profit` AKShare aliases so `PARENT_NETPROFIT` is primary.
- Modify: `src/financial_report_llm_extractor/structured_sources/mapping.py`
  - Preserve non-selected related source candidates as policy evidence after alias precedence.
- Create: `src/financial_report_llm_extractor/structured_sources/source_policy.py`
  - Classify semantic mismatches, FX-like ratios, suspected currency metadata, and single-source unverified fields.
  - Resolve primary source selection with warnings and verification flags.
- Modify: `src/financial_report_llm_extractor/structured_sources/export.py`
  - Add policy selection metadata to `SourceFirstExportItem`.
  - Accept an optional source policy report in `build_source_first_export()`.
- Modify: `src/financial_report_llm_extractor/structured_sources/provider_baseline_replay.py`
  - Build source policy reports for each slice and use selected coverage metrics in top-level summaries.
  - Write `source_policy_report.json` per slice.
- Test: `tests/test_source_mapping_catalog.py`
  - Validate policy parsing and catalog regression for `net_profit`.
- Test: `tests/test_source_mapping.py`
  - Validate related source candidates survive as policy evidence candidates.
- Test: `tests/test_source_policy.py`
  - Cover classification and resolver behavior.
- Test: `tests/test_source_review_export.py`
  - Cover export of selected primary candidates with warnings and PDF verification.
- Test: `tests/test_provider_baseline_replay.py`
  - Cover top-level selected coverage, clean coverage, and conflict categories on checked-in fixtures.

## Task 1: Add Source Policy Catalog Contracts

**Files:**
- Modify: `tests/test_source_mapping_catalog.py`
- Modify: `src/financial_report_llm_extractor/structured_sources/catalog.py`

- [ ] **Step 1: Write the failing catalog policy parsing test**

Add this test to `tests/test_source_mapping_catalog.py`:

```python
def test_source_mapping_catalog_loads_optional_source_policy(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(
        json.dumps(
            {
                "catalog_id": "test",
                "version": "1",
                "priorities": [{"priority": "P0", "fields": ["net_profit"]}],
                "source_mappings": {
                    "net_profit": {
                        "value_type": "money",
                        "statement_type": "income_statement",
                        "domain": "income_statement",
                        "source_mode": "direct",
                        "primary_route": "akshare_direct",
                        "verification_status": "verified",
                        "currency_requirement": "required",
                        "unit_requirement": "required",
                        "fallback_policy": "pdf_allowed",
                        "source_aliases": {
                            "akshare": [
                                "PARENT_NETPROFIT",
                                "归属于母公司股东的净利润",
                                "NETPROFIT",
                                "净利润"
                            ],
                            "yahoo": ["Net Income"]
                        },
                        "source_policy": {
                            "semantic_concept": (
                                "profit attributable to parent-company shareholders"
                            ),
                            "semantic_variants": {
                                "akshare": {
                                    "primary": [
                                        "PARENT_NETPROFIT",
                                        "归属于母公司股东的净利润"
                                    ],
                                    "related": ["NETPROFIT", "净利润"]
                                },
                                "yahoo": {"primary": ["Net Income"]}
                            },
                            "market_policies": {
                                "CN": {
                                    "primary_route": "akshare_direct",
                                    "cross_check_routes": ["yahoo_direct"],
                                    "on_conflict": "select_primary_require_pdf",
                                    "single_source_requires_pdf": False
                                }
                            },
                            "verification_requirement": "pdf_required_on_conflict"
                        }
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    catalog = load_source_mapping_catalog(catalog_path, priorities=("P0",))

    policy = catalog.entries["net_profit"].source_policy
    assert policy is not None
    assert (
        policy.semantic_concept
        == "profit attributable to parent-company shareholders"
    )
    assert policy.semantic_variants["akshare"].primary == (
        "PARENT_NETPROFIT",
        "归属于母公司股东的净利润",
    )
    assert policy.semantic_variants["akshare"].related == ("NETPROFIT", "净利润")
    assert policy.market_policies["CN"].on_conflict == "select_primary_require_pdf"
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
uv run pytest tests/test_source_mapping_catalog.py::test_source_mapping_catalog_loads_optional_source_policy -v
```

Expected: fail because `SourceMappingEntry` has no `source_policy`.

- [ ] **Step 3: Implement catalog dataclasses and parser**

In `src/financial_report_llm_extractor/structured_sources/catalog.py`, add these dataclasses above `SourceMappingEntry`:

```python
@dataclass(frozen=True)
class SourceSemanticVariants:
    primary: tuple[str, ...] = field(default_factory=tuple)
    related: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MarketSourcePolicy:
    primary_route: str
    cross_check_routes: tuple[str, ...] = field(default_factory=tuple)
    on_conflict: str = "preserve_conflict"
    single_source_requires_pdf: bool = False


@dataclass(frozen=True)
class SourcePolicy:
    semantic_concept: str
    semantic_variants: dict[str, SourceSemanticVariants] = field(default_factory=dict)
    market_policies: dict[str, MarketSourcePolicy] = field(default_factory=dict)
    verification_requirement: str = "none"
```

Add the field to `SourceMappingEntry`:

```python
source_policy: SourcePolicy | None = None
```

Add parser helpers:

```python
def _parse_source_policy(raw_policy: object) -> SourcePolicy | None:
    if raw_policy is None:
        return None
    if not isinstance(raw_policy, dict):
        raise ValueError("source_policy must be an object")

    raw_variants = raw_policy.get("semantic_variants", {})
    if not isinstance(raw_variants, dict):
        raise ValueError("source_policy semantic_variants must be an object")
    variants: dict[str, SourceSemanticVariants] = {}
    for source, value in raw_variants.items():
        if not isinstance(value, dict):
            raise ValueError("source_policy semantic variant must be an object")
        variants[str(source)] = SourceSemanticVariants(
            primary=tuple(str(item) for item in value.get("primary", [])),
            related=tuple(str(item) for item in value.get("related", [])),
        )

    raw_market_policies = raw_policy.get("market_policies", {})
    if not isinstance(raw_market_policies, dict):
        raise ValueError("source_policy market_policies must be an object")
    market_policies: dict[str, MarketSourcePolicy] = {}
    for market, value in raw_market_policies.items():
        if not isinstance(value, dict):
            raise ValueError("source_policy market policy must be an object")
        market_policies[str(market)] = MarketSourcePolicy(
            primary_route=str(value.get("primary_route", "")),
            cross_check_routes=tuple(
                str(item) for item in value.get("cross_check_routes", [])
            ),
            on_conflict=str(value.get("on_conflict", "preserve_conflict")),
            single_source_requires_pdf=bool(
                value.get("single_source_requires_pdf", False)
            ),
        )

    return SourcePolicy(
        semantic_concept=str(raw_policy.get("semantic_concept", "")),
        semantic_variants=variants,
        market_policies=market_policies,
        verification_requirement=str(
            raw_policy.get("verification_requirement", "none")
        ),
    )
```

Pass `source_policy=_parse_source_policy(mapping.get("source_policy"))` when constructing `SourceMappingEntry`.

- [ ] **Step 4: Run catalog tests**

Run:

```bash
uv run pytest tests/test_source_mapping_catalog.py -v
```

Expected: pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add src/financial_report_llm_extractor/structured_sources/catalog.py tests/test_source_mapping_catalog.py
git commit -m "feat: add source policy catalog metadata"
```

## Task 2: Update Minimal Catalog Semantics

**Files:**
- Modify: `field_catalog/turtle_v015_source_mapping_minimal.json`
- Modify: `tests/test_source_mapping_catalog.py`

- [ ] **Step 1: Write failing real catalog regression tests**

Add these tests to `tests/test_source_mapping_catalog.py`:

```python
def test_minimal_source_mapping_net_profit_prefers_parent_profit() -> None:
    catalog = load_source_mapping_catalog(
        Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        priorities=("P0", "P1"),
    )

    entry = catalog.entries["net_profit"]

    assert entry.source_aliases["akshare"][:2] == (
        "PARENT_NETPROFIT",
        "归属于母公司股东的净利润",
    )
    assert "NETPROFIT" in entry.source_aliases["akshare"][2:]
    assert entry.source_policy is not None
    assert (
        entry.source_policy.semantic_concept
        == "profit attributable to parent-company shareholders"
    )


def test_minimal_source_mapping_revenue_declares_operating_revenue_policy() -> None:
    catalog = load_source_mapping_catalog(
        Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        priorities=("P0", "P1"),
    )

    entry = catalog.entries["revenue"]

    assert entry.source_aliases["akshare"][:2] == ("OPERATE_INCOME", "营业收入")
    assert entry.source_policy is not None
    assert entry.source_policy.semantic_variants["akshare"].related == (
        "TOTAL_OPERATE_INCOME",
        "营业总收入",
    )
```

- [ ] **Step 2: Run focused tests and verify they fail**

Run:

```bash
uv run pytest tests/test_source_mapping_catalog.py::test_minimal_source_mapping_net_profit_prefers_parent_profit tests/test_source_mapping_catalog.py::test_minimal_source_mapping_revenue_declares_operating_revenue_policy -v
```

Expected: fail because catalog aliases/policies are not yet updated.

- [ ] **Step 3: Update `revenue` source policy**

In `field_catalog/turtle_v015_source_mapping_minimal.json`, update `revenue` so AKShare aliases start with exact raw codes and include policy:

```json
"source_aliases": {
  "akshare": [
    "OPERATE_INCOME",
    "营业收入",
    "Revenue",
    "TOTAL_OPERATE_INCOME",
    "营业总收入",
    "Total revenue"
  ],
  "yahoo": [
    "Total Revenue",
    "Operating Revenue"
  ]
},
"source_policy": {
  "semantic_concept": "operating revenue",
  "semantic_variants": {
    "akshare": {
      "primary": ["OPERATE_INCOME", "营业收入"],
      "related": ["TOTAL_OPERATE_INCOME", "营业总收入"]
    },
    "yahoo": {
      "primary": ["Total Revenue", "Operating Revenue"]
    }
  },
  "market_policies": {
    "CN": {
      "primary_route": "akshare_direct",
      "cross_check_routes": ["yahoo_direct"],
      "on_conflict": "select_primary_require_pdf",
      "single_source_requires_pdf": false
    },
    "HK": {
      "primary_route": "yahoo_direct",
      "cross_check_routes": ["akshare_direct"],
      "on_conflict": "select_primary_require_pdf",
      "single_source_requires_pdf": true
    }
  },
  "verification_requirement": "pdf_required_on_conflict"
}
```

- [ ] **Step 4: Update `net_profit` source policy**

In the same catalog file, update `net_profit`:

```json
"source_aliases": {
  "akshare": [
    "PARENT_NETPROFIT",
    "归属于母公司股东的净利润",
    "Profit attributable to shareholders",
    "NETPROFIT",
    "净利润"
  ],
  "yahoo": [
    "Net Income",
    "Net Income Common Stockholders"
  ]
},
"source_policy": {
  "semantic_concept": "profit attributable to parent-company shareholders",
  "semantic_variants": {
    "akshare": {
      "primary": ["PARENT_NETPROFIT", "归属于母公司股东的净利润"],
      "related": ["NETPROFIT", "净利润"]
    },
    "yahoo": {
      "primary": ["Net Income", "Net Income Common Stockholders"]
    }
  },
  "market_policies": {
    "CN": {
      "primary_route": "akshare_direct",
      "cross_check_routes": ["yahoo_direct"],
      "on_conflict": "select_primary_require_pdf",
      "single_source_requires_pdf": false
    },
    "HK": {
      "primary_route": "yahoo_direct",
      "cross_check_routes": ["akshare_direct"],
      "on_conflict": "select_primary_require_pdf",
      "single_source_requires_pdf": true
    }
  },
  "verification_requirement": "pdf_required_on_conflict"
}
```

- [ ] **Step 5: Add HK balance-sheet/gross-profit policies**

For `gross_profit`, `total_assets`, `total_cur_assets`, `total_cur_liab`, and `total_liabilities`, add a `source_policy` with HK AKShare primary:

```json
"source_policy": {
  "semantic_concept": "reported statement line",
  "semantic_variants": {},
  "market_policies": {
    "HK": {
      "primary_route": "akshare_direct",
      "cross_check_routes": ["yahoo_direct"],
      "on_conflict": "select_primary_require_pdf",
      "single_source_requires_pdf": false
    },
    "CN": {
      "primary_route": "akshare_direct",
      "cross_check_routes": ["yahoo_direct"],
      "on_conflict": "preserve_conflict",
      "single_source_requires_pdf": false
    }
  },
  "verification_requirement": "pdf_required_on_conflict"
}
```

- [ ] **Step 6: Run catalog tests**

Run:

```bash
uv run pytest tests/test_source_mapping_catalog.py -v
```

Expected: pass.

- [ ] **Step 7: Commit Task 2**

```bash
git add field_catalog/turtle_v015_source_mapping_minimal.json tests/test_source_mapping_catalog.py
git commit -m "feat: define source policy for conflict fields"
```

## Task 3: Add Policy Evidence Candidates And Conflict Classification

**Files:**
- Modify: `tests/test_source_mapping.py`
- Modify: `src/financial_report_llm_extractor/structured_sources/mapping.py`
- Create: `src/financial_report_llm_extractor/structured_sources/source_policy.py`
- Create: `tests/test_source_policy.py`

- [ ] **Step 1: Write the failing policy evidence candidate mapping test**

Add this test to `tests/test_source_mapping.py`:

```python
def test_map_source_inventory_preserves_related_policy_evidence_candidates() -> None:
    catalog = SourceMappingCatalog(
        catalog_id="test",
        version="1",
        entries={
            "revenue": _entry(
                "revenue",
                statement_type="income_statement",
                source_aliases={
                    "akshare": (
                        "OPERATE_INCOME",
                        "营业收入",
                        "TOTAL_OPERATE_INCOME",
                        "营业总收入",
                    ),
                    "yahoo": ("Total Revenue",),
                },
            )
        },
    )
    records = (
        _record(
            "营业收入",
            "168838102514.79",
            Decimal("168838102514.79"),
            raw_field_code="OPERATE_INCOME",
        ),
        _record(
            "营业总收入",
            "172054171890.91",
            Decimal("172054171890.91"),
            raw_field_code="TOTAL_OPERATE_INCOME",
        ),
        _record(
            "Total Revenue",
            "172054171890.91",
            Decimal("172054171890.91"),
            source="yahoo",
            raw_field_code=None,
        ),
    )

    result = map_source_inventory(catalog, records)

    mapped = result.fields["revenue"]
    assert mapped.status == "ambiguous"
    assert [candidate.raw_field_code for candidate in mapped.candidates] == [
        "OPERATE_INCOME",
        None,
    ]
    assert [
        candidate.raw_field_code
        for candidate in mapped.policy_evidence_candidates
    ] == ["TOTAL_OPERATE_INCOME"]
```

If the existing `_record()` helper does not accept `raw_field_code`, extend it with an optional `raw_field_code: str | None = None` parameter and pass it into `SourceInventoryRecord`.

- [ ] **Step 2: Run the focused mapping test and verify it fails**

Run:

```bash
uv run pytest tests/test_source_mapping.py::test_map_source_inventory_preserves_related_policy_evidence_candidates -v
```

Expected: fail because `MappedTurtleField` has no `policy_evidence_candidates`.

- [ ] **Step 3: Preserve policy evidence candidates in mapping**

In `src/financial_report_llm_extractor/structured_sources/mapping.py`, add this field to `MappedTurtleField`:

```python
policy_evidence_candidates: tuple[TurtleMappingCandidate, ...] = field(default_factory=tuple)
```

Add it to `MappedTurtleField.to_dict()`:

```python
"policy_evidence_candidates": [
    candidate.to_dict() for candidate in self.policy_evidence_candidates
],
```

In `_map_direct_field()`, keep valid candidates before alias precedence:

```python
valid_candidates = tuple(
    candidate for candidate in matched_candidates if not candidate.errors
)
```

Use `valid_candidates` for the blocked check and alias precedence:

```python
if not valid_candidates:
    return MappedTurtleField(...)
candidates = _apply_alias_precedence(entry, valid_candidates)
policy_evidence_candidates = tuple(
    candidate for candidate in valid_candidates if candidate not in candidates
)
```

Pass `policy_evidence_candidates=policy_evidence_candidates` in both the ambiguous and single-candidate `MappedTurtleField` returns.

- [ ] **Step 4: Run source mapping tests**

Run:

```bash
uv run pytest tests/test_source_mapping.py -v
```

Expected: pass.

- [ ] **Step 5: Write tests for semantic mismatch and source selection**

Create `tests/test_source_policy.py` with these tests and helpers:

```python
from decimal import Decimal

from financial_report_llm_extractor.structured_sources.catalog import (
    MarketSourcePolicy,
    SourceMappingCatalog,
    SourceMappingEntry,
    SourcePolicy,
    SourceSemanticVariants,
)
from financial_report_llm_extractor.structured_sources.mapping import (
    MappedTurtleField,
    TurtleMappingCandidate,
    TurtleMappingResult,
)
from financial_report_llm_extractor.structured_sources.models import SourceEvidence
from financial_report_llm_extractor.structured_sources.reconciliation import (
    reconcile_mapped_fields,
)
from financial_report_llm_extractor.structured_sources.source_policy import (
    build_source_policy_report,
)


def test_source_policy_classifies_revenue_semantic_mismatch_and_selects_primary() -> None:
    catalog = _catalog(
        "revenue",
        SourcePolicy(
            semantic_concept="operating revenue",
            semantic_variants={
                "akshare": SourceSemanticVariants(
                    primary=("OPERATE_INCOME", "营业收入"),
                    related=("TOTAL_OPERATE_INCOME", "营业总收入"),
                ),
                "yahoo": SourceSemanticVariants(primary=("Total Revenue",)),
            },
            market_policies={
                "CN": MarketSourcePolicy(
                    primary_route="akshare_direct",
                    cross_check_routes=("yahoo_direct",),
                    on_conflict="select_primary_require_pdf",
                )
            },
            verification_requirement="pdf_required_on_conflict",
        ),
    )
    mapping = _mapping(
        "revenue",
        (
            _candidate(
                source="akshare",
                raw_field_name="营业收入",
                raw_field_code="OPERATE_INCOME",
                normalized_value=Decimal("168838102514.79"),
                currency="CNY",
            ),
            _candidate(
                source="yahoo",
                raw_field_name="Total Revenue",
                raw_field_code=None,
                normalized_value=Decimal("172054171890.91"),
                currency="CNY",
            ),
        ),
    )
    reconciliation = reconcile_mapped_fields(mapping)

    report = build_source_policy_report(
        catalog,
        mapping,
        reconciliation,
        market="CN",
        company_id="600519",
    )

    item = report.items["revenue"]
    assert item.selection_status == "selected_primary"
    assert item.selected_candidate is not None
    assert item.selected_candidate.source == "akshare"
    assert item.selected_candidate.raw_field_code == "OPERATE_INCOME"
    assert item.verification_required is True
    assert item.conflict_classifications == ("semantic_mismatch",)
```

Add a stable-ratio test:

```python
def test_source_policy_classifies_hk_fx_like_ratio_across_multiple_fields() -> None:
    catalog = SourceMappingCatalog(
        catalog_id="test",
        version="1",
        entries={
            field_id: _entry(
                field_id,
                SourcePolicy(
                    semantic_concept="reported statement line",
                    market_policies={
                        "HK": MarketSourcePolicy(
                            primary_route="akshare_direct",
                            cross_check_routes=("yahoo_direct",),
                            on_conflict="select_primary_require_pdf",
                        )
                    },
                    verification_requirement="pdf_required_on_conflict",
                ),
            )
            for field_id in ("total_assets", "total_cur_assets", "total_liabilities")
        },
    )
    mapping = TurtleMappingResult(
        catalog_id="test",
        catalog_version="1",
        fields={
            "total_assets": _field("total_assets", Decimal("100"), Decimal("110.71499745")),
            "total_cur_assets": _field("total_cur_assets", Decimal("50"), Decimal("55.357498725")),
            "total_liabilities": _field("total_liabilities", Decimal("20"), Decimal("22.14299949")),
        },
    )
    reconciliation = reconcile_mapped_fields(mapping)

    report = build_source_policy_report(
        catalog,
        mapping,
        reconciliation,
        market="HK",
        company_id="00001",
    )

    assert report.items["total_assets"].selection_status == "selected_primary"
    assert report.items["total_assets"].selected_candidate is not None
    assert report.items["total_assets"].selected_candidate.source == "akshare"
    assert report.items["total_assets"].verification_required is True
    assert report.items["total_assets"].conflict_classifications == (
        "fx_like_ratio",
        "metadata_currency_suspected",
    )
```

Use these helpers. The `policy_evidence_candidates` value in `_mapping()` is required because real `600519` revenue needs the non-selected AKShare `TOTAL_OPERATE_INCOME` candidate to prove that Yahoo aligns with a related semantic variant:

```python
def _catalog(field_id: str, policy: SourcePolicy) -> SourceMappingCatalog:
    return SourceMappingCatalog(
        catalog_id="test",
        version="1",
        entries={field_id: _entry(field_id, policy)},
    )


def _entry(field_id: str, policy: SourcePolicy) -> SourceMappingEntry:
    return SourceMappingEntry(
        field_id=field_id,
        priority="P0",
        value_type="money",
        statement_type="income_statement",
        currency_requirement="required",
        unit_requirement="required",
        source_aliases={"akshare": ("Revenue",), "yahoo": ("Total Revenue",)},
        source_policy=policy,
    )


def _mapping(
    field_id: str,
    candidates: tuple[TurtleMappingCandidate, ...],
) -> TurtleMappingResult:
    return TurtleMappingResult(
        catalog_id="test",
        catalog_version="1",
        fields={
            field_id: MappedTurtleField(
                field_id=field_id,
                status="ambiguous",
                candidates=candidates,
                policy_evidence_candidates=(
                    _candidate(
                        source="akshare",
                        raw_field_name="营业总收入",
                        raw_field_code="TOTAL_OPERATE_INCOME",
                        normalized_value=Decimal("172054171890.91"),
                        currency="CNY",
                    ),
                )
                if field_id == "revenue"
                else (),
                errors=("multiple source candidates matched catalog aliases",),
            )
        },
    )


def _field(
    field_id: str,
    akshare_value: Decimal,
    yahoo_value: Decimal,
) -> MappedTurtleField:
    return MappedTurtleField(
        field_id=field_id,
        status="ambiguous",
        candidates=(
            _candidate("akshare", "总资产", "TOTAL_ASSETS", akshare_value, currency="HKD"),
            _candidate("yahoo", "Total Assets", None, yahoo_value, currency="HKD"),
        ),
        errors=("multiple source candidates matched catalog aliases",),
    )


def _candidate(
    source: str,
    raw_field_name: str,
    raw_field_code: str | None,
    normalized_value: Decimal,
    *,
    currency: str,
) -> TurtleMappingCandidate:
    return TurtleMappingCandidate(
        source=source,  # type: ignore[arg-type]
        raw_field_name=raw_field_name,
        raw_field_code=raw_field_code,
        raw_value=str(normalized_value),
        value=normalized_value,
        normalized_value=normalized_value,
        currency=currency,  # type: ignore[arg-type]
        unit="raw" if source == "yahoo" else currency,
        canonical_unit=currency,  # type: ignore[arg-type]
        period="2025-12-31",
        scope="unknown",
        source_evidence=(
            SourceEvidence(
                source=source,  # type: ignore[arg-type]
                adapter=source,
                function="fixture",
                artifact_id=f"{source}_artifact",
                raw_record_id=f"{source}:{raw_field_name}",
                raw_field_name=raw_field_name,
                raw_field_code=raw_field_code,
            ),
        ),
    )
```

- [ ] **Step 6: Run tests and verify they fail**

Run:

```bash
uv run pytest tests/test_source_policy.py -v
```

Expected: fail because `source_policy.py` does not exist.

- [ ] **Step 7: Implement source policy report dataclasses**

Create `src/financial_report_llm_extractor/structured_sources/source_policy.py`:

```python
"""Source policy selection and conflict classification."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Literal

from financial_report_llm_extractor.structured_sources.catalog import (
    MarketSourcePolicy,
    SourceMappingCatalog,
    SourceMappingEntry,
)
from financial_report_llm_extractor.structured_sources.mapping import (
    MappedTurtleField,
    TurtleMappingCandidate,
    TurtleMappingResult,
)
from financial_report_llm_extractor.structured_sources.reconciliation import (
    ReconciliationReport,
    ReconciliationStatus,
)

ConflictClassification = Literal[
    "semantic_mismatch",
    "fx_like_ratio",
    "metadata_currency_suspected",
    "normalized_value_conflict",
    "missing_source_candidate",
    "single_source_unverified",
    "currency_metadata_required",
]
SelectionStatus = Literal[
    "selected_primary",
    "selected_single_source",
    "unresolved_conflict",
    "missing",
    "blocked",
]


@dataclass(frozen=True)
class SourcePolicyItem:
    field_id: str
    selection_status: SelectionStatus
    selected_candidate: TurtleMappingCandidate | None = None
    conflict_classifications: tuple[ConflictClassification, ...] = field(default_factory=tuple)
    verification_required: bool = False
    warnings: tuple[str, ...] = field(default_factory=tuple)
    reconciliation_status: ReconciliationStatus | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "field_id": self.field_id,
            "selection_status": self.selection_status,
            "selected_candidate": (
                self.selected_candidate.to_dict()
                if self.selected_candidate is not None
                else None
            ),
            "conflict_classifications": list(self.conflict_classifications),
            "verification_required": self.verification_required,
            "warnings": list(self.warnings),
            "reconciliation_status": self.reconciliation_status,
        }


@dataclass(frozen=True)
class SourcePolicyReport:
    catalog_id: str
    catalog_version: str
    company_id: str | None
    market: str | None
    items: dict[str, SourcePolicyItem]

    def to_dict(self) -> dict[str, object]:
        return {
            "catalog_id": self.catalog_id,
            "catalog_version": self.catalog_version,
            "company_id": self.company_id,
            "market": self.market,
            "items": {
                field_id: self.items[field_id].to_dict()
                for field_id in sorted(self.items)
            },
        }
```

- [ ] **Step 8: Implement report builder and helpers**

Continue in the same file:

```python
def build_source_policy_report(
    catalog: SourceMappingCatalog,
    mapping: TurtleMappingResult,
    reconciliation: ReconciliationReport,
    *,
    market: str | None = None,
    company_id: str | None = None,
) -> SourcePolicyReport:
    ratio_fields = _fx_like_fields(mapping)
    items: dict[str, SourcePolicyItem] = {}
    for field_id, field in mapping.fields.items():
        entry = catalog.entries[field_id]
        reconciliation_item = reconciliation.items.get(field_id)
        reconciliation_status = (
            reconciliation_item.status if reconciliation_item is not None else None
        )
        items[field_id] = _resolve_field(
            entry,
            field,
            market=market,
            reconciliation_status=reconciliation_status,
            fx_like=field_id in ratio_fields,
        )
    return SourcePolicyReport(
        catalog_id=mapping.catalog_id,
        catalog_version=mapping.catalog_version,
        company_id=company_id,
        market=market,
        items=items,
    )


def write_source_policy_report(report: SourcePolicyReport, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return output_path


def _resolve_field(
    entry: SourceMappingEntry,
    field: MappedTurtleField,
    *,
    market: str | None,
    reconciliation_status: ReconciliationStatus | None,
    fx_like: bool,
) -> SourcePolicyItem:
    if field.status == "missing":
        return SourcePolicyItem(
            field_id=field.field_id,
            selection_status="missing",
            conflict_classifications=("missing_source_candidate",),
            reconciliation_status=reconciliation_status,
        )
    if field.status == "blocked":
        return SourcePolicyItem(
            field_id=field.field_id,
            selection_status="blocked",
            reconciliation_status=reconciliation_status,
        )
    if field.status in {"present", "derived"} and field.candidates:
        return _resolve_single_source(entry, field, market, reconciliation_status)
    if reconciliation_status in {"equivalent", "close"}:
        return SourcePolicyItem(
            field_id=field.field_id,
            selection_status="selected_primary",
            selected_candidate=_primary_candidate(entry, field, market) or field.candidates[0],
            reconciliation_status=reconciliation_status,
        )

    classifications = _classifications(entry, field, fx_like=fx_like)
    candidate = _primary_candidate(entry, field, market)
    market_policy = _market_policy(entry, market)
    if candidate is not None and _requires_currency_metadata(candidate):
        return SourcePolicyItem(
            field_id=field.field_id,
            selection_status="unresolved_conflict",
            conflict_classifications=classifications
            + ("currency_metadata_required",),
            verification_required=True,
            warnings=("selected primary candidate lacks proven currency metadata",),
            reconciliation_status=reconciliation_status,
        )
    if (
        candidate is not None
        and market_policy is not None
        and market_policy.on_conflict == "select_primary_require_pdf"
    ):
        return SourcePolicyItem(
            field_id=field.field_id,
            selection_status="selected_primary",
            selected_candidate=candidate,
            conflict_classifications=classifications,
            verification_required=True,
            warnings=tuple(
                f"source policy selected primary candidate despite {classification}"
                for classification in classifications
            ),
            reconciliation_status=reconciliation_status,
        )
    return SourcePolicyItem(
        field_id=field.field_id,
        selection_status="unresolved_conflict",
        conflict_classifications=classifications or ("normalized_value_conflict",),
        verification_required=True,
        reconciliation_status=reconciliation_status,
    )
```

- [ ] **Step 9: Implement classification helpers**

Continue in the same file:

```python
def _resolve_single_source(
    entry: SourceMappingEntry,
    field: MappedTurtleField,
    market: str | None,
    reconciliation_status: ReconciliationStatus | None,
) -> SourcePolicyItem:
    candidate = field.candidates[0]
    market_policy = _market_policy(entry, market)
    requires_pdf = bool(
        market_policy is not None and market_policy.single_source_requires_pdf
    )
    classifications: tuple[ConflictClassification, ...] = (
        ("single_source_unverified",) if requires_pdf else ()
    )
    return SourcePolicyItem(
        field_id=field.field_id,
        selection_status="selected_single_source",
        selected_candidate=candidate,
        conflict_classifications=classifications,
        verification_required=requires_pdf,
        warnings=(
            ("single source candidate requires PDF verification",)
            if requires_pdf
            else ()
        ),
        reconciliation_status=reconciliation_status,
    )


def _classifications(
    entry: SourceMappingEntry,
    field: MappedTurtleField,
    *,
    fx_like: bool,
) -> tuple[ConflictClassification, ...]:
    classifications: list[ConflictClassification] = []
    if _semantic_mismatch(entry, field):
        classifications.append("semantic_mismatch")
    if fx_like:
        classifications.extend(["fx_like_ratio", "metadata_currency_suspected"])
    if not classifications and _values_differ(field):
        classifications.append("normalized_value_conflict")
    return tuple(classifications)


def _semantic_mismatch(entry: SourceMappingEntry, field: MappedTurtleField) -> bool:
    policy = entry.source_policy
    if policy is None:
        return False
    for candidate in field.candidates + field.policy_evidence_candidates:
        variants = policy.semantic_variants.get(candidate.source)
        if variants is None:
            continue
        label = candidate.raw_field_code or candidate.raw_field_name
        if label in variants.related:
            return True
    return False


def _values_differ(field: MappedTurtleField) -> bool:
    values = {
        candidate.normalized_value
        for candidate in field.candidates
        if candidate.normalized_value is not None
    }
    return len(values) > 1


def _requires_currency_metadata(candidate: TurtleMappingCandidate) -> bool:
    return (
        candidate.currency in {"unknown", "ambiguous"}
        or candidate.unit is None
        or candidate.canonical_unit is None
    )


def _market_policy(
    entry: SourceMappingEntry,
    market: str | None,
) -> MarketSourcePolicy | None:
    if entry.source_policy is None or market is None:
        return None
    return entry.source_policy.market_policies.get(market)


def _primary_candidate(
    entry: SourceMappingEntry,
    field: MappedTurtleField,
    market: str | None,
) -> TurtleMappingCandidate | None:
    market_policy = _market_policy(entry, market)
    if market_policy is None:
        return None
    primary_source = market_policy.primary_route.split("_", 1)[0]
    source_candidates = [
        candidate
        for candidate in field.candidates
        if candidate.source == primary_source
    ]
    if not source_candidates:
        return None
    if entry.source_policy is None:
        return source_candidates[0]
    variants = entry.source_policy.semantic_variants.get(primary_source)
    if variants is None:
        return source_candidates[0]
    for primary_label in variants.primary:
        for candidate in source_candidates:
            if candidate.raw_field_code == primary_label or candidate.raw_field_name == primary_label:
                return candidate
    return source_candidates[0]
```

Add the ratio detector:

```python
def _fx_like_fields(
    mapping: TurtleMappingResult,
    *,
    relative_tolerance: Decimal = Decimal("0.001"),
) -> set[str]:
    ratios: list[tuple[str, Decimal]] = []
    for field_id, field in mapping.fields.items():
        if len(field.candidates) != 2:
            continue
        left, right = field.candidates
        if left.normalized_value in {None, Decimal("0")}:
            continue
        if right.normalized_value is None:
            continue
        if left.period != right.period:
            continue
        if {left.source, right.source} != {"akshare", "yahoo"}:
            continue
        base = left.normalized_value
        other = right.normalized_value
        if base is None or other is None:
            continue
        ratio = other / base
        if ratio == 1:
            continue
        ratios.append((field_id, ratio))
    for field_id, ratio in ratios:
        similar = [
            other_field_id
            for other_field_id, other_ratio in ratios
            if _relative_difference(ratio, other_ratio) <= relative_tolerance
        ]
        if len(similar) >= 3:
            return set(similar)
    return set()


def _relative_difference(left: Decimal, right: Decimal) -> Decimal:
    denominator = max(abs(left), abs(right))
    if denominator == 0:
        return Decimal("0")
    return abs(left - right) / denominator
```

- [ ] **Step 10: Run source policy tests and static checks**

Run:

```bash
uv run pytest tests/test_source_policy.py -v
uv run ruff check src/financial_report_llm_extractor/structured_sources/source_policy.py tests/test_source_policy.py
uv run mypy src/financial_report_llm_extractor/structured_sources/source_policy.py tests/test_source_policy.py
```

Expected: pass.

- [ ] **Step 11: Commit Task 3**

```bash
git add src/financial_report_llm_extractor/structured_sources/mapping.py src/financial_report_llm_extractor/structured_sources/source_policy.py tests/test_source_mapping.py tests/test_source_policy.py
git commit -m "feat: classify source conflicts by policy"
```

## Task 4: Integrate Policy Selection Into Export

**Files:**
- Modify: `tests/test_source_review_export.py`
- Modify: `src/financial_report_llm_extractor/structured_sources/export.py`

- [ ] **Step 1: Write failing export test**

Add this test to `tests/test_source_review_export.py`:

```python
def test_source_first_export_preserves_policy_selected_conflict_metadata() -> None:
    mapping = TurtleMappingResult(
        catalog_id="test",
        catalog_version="1",
        fields={
            "revenue": MappedTurtleField(
                field_id="revenue",
                status="ambiguous",
                candidates=(
                    _candidate("akshare", Decimal("168"), canonical_unit="CNY"),
                    _candidate("yahoo", Decimal("172"), canonical_unit="CNY"),
                ),
                errors=("multiple source candidates matched catalog aliases",),
            )
        },
    )
    reconciliation = reconcile_mapped_fields(mapping)
    policy_report = SourcePolicyReport(
        catalog_id="test",
        catalog_version="1",
        company_id="600519",
        market="CN",
        items={
            "revenue": SourcePolicyItem(
                field_id="revenue",
                selection_status="selected_primary",
                selected_candidate=mapping.fields["revenue"].candidates[0],
                conflict_classifications=("semantic_mismatch",),
                verification_required=True,
                warnings=(
                    "source policy selected primary candidate despite semantic_mismatch",
                ),
                reconciliation_status="conflict",
            )
        },
    )

    result = build_source_first_export(
        mapping,
        reconciliation,
        profile="source_only",
        source_policy_report=policy_report,
    )

    item = result.items["revenue"]
    assert item.status == "present"
    assert item.selection_status == "selected_primary"
    assert item.selected_source == "akshare"
    assert item.verification_required is True
    assert item.conflict_classifications == ("semantic_mismatch",)
    assert item.warnings == (
        "source policy selected primary candidate despite semantic_mismatch",
    )
    assert item.value == Decimal("168")
    assert result.summary["selected_with_warnings_fields"] == ["revenue"]
    assert result.summary["fields_requiring_pdf_evidence"] == ["revenue"]
```

Add imports:

```python
from financial_report_llm_extractor.structured_sources.source_policy import (
    SourcePolicyItem,
    SourcePolicyReport,
)
```

- [ ] **Step 2: Run focused test and verify it fails**

Run:

```bash
uv run pytest tests/test_source_review_export.py::test_source_first_export_preserves_policy_selected_conflict_metadata -v
```

Expected: fail because export does not accept `source_policy_report`.

- [ ] **Step 3: Add export metadata fields**

In `src/financial_report_llm_extractor/structured_sources/export.py`, import `SourcePolicyReport` and add fields to `SourceFirstExportItem`:

```python
selection_status: str | None = None
selected_source: str | None = None
verification_required: bool = False
conflict_classifications: tuple[str, ...] = field(default_factory=tuple)
review_notes: tuple[str, ...] = field(default_factory=tuple)
```

Add these keys in `to_dict()`:

```python
"selection_status": self.selection_status,
"selected_source": self.selected_source,
"verification_required": self.verification_required,
"conflict_classifications": list(self.conflict_classifications),
"review_notes": list(self.review_notes),
```

- [ ] **Step 4: Thread policy report into export building**

Change the signature:

```python
def build_source_first_export(
    mapping_result: TurtleMappingResult,
    reconciliation_report: ReconciliationReport,
    *,
    profile: ExportProfile,
    pdf_evidence_by_field: dict[str, tuple[Evidence, ...]] | None = None,
    source_policy_report: SourcePolicyReport | None = None,
) -> SourceFirstExportResult:
```

Pass `policy_item=source_policy_report.items.get(field_id)` into `_build_item()`.

In `_build_item()`, if `policy_item.selection_status` is `selected_primary` or `selected_single_source` and `selected_candidate` is present:

```python
candidate = policy_item.selected_candidate
status = "present"
value = candidate.value
normalized_value = candidate.normalized_value
currency = candidate.currency
unit = candidate.unit
canonical_unit = candidate.canonical_unit
period = candidate.period
scope = candidate.scope
source_evidence = candidate.source_evidence
errors = ()
warnings = policy_item.warnings
selection_status = policy_item.selection_status
selected_source = candidate.source
verification_required = policy_item.verification_required
conflict_classifications = policy_item.conflict_classifications
review_notes = tuple(policy_item.conflict_classifications)
```

If `verification_required` is true and `profile == "pdf_required"` with no PDF evidence, set `status = "needs_pdf_evidence"` while retaining selected metadata.

- [ ] **Step 5: Extend review summary**

In `build_review_summary()`, add:

```python
"selected_with_warnings_fields": sorted(
    field_id
    for field_id, item in result.items.items()
    if item.status == "present" and (item.warnings or item.verification_required)
),
"unresolved_conflict_fields": _fields_with_status(result, "conflict"),
"fields_requiring_pdf_evidence": sorted(
    field_id
    for field_id, item in result.items.items()
    if item.status == "needs_pdf_evidence" or item.verification_required
),
```

Keep existing keys for compatibility.

- [ ] **Step 6: Run export tests**

Run:

```bash
uv run pytest tests/test_source_review_export.py -v
```

Expected: pass.

- [ ] **Step 7: Commit Task 4**

```bash
git add src/financial_report_llm_extractor/structured_sources/export.py tests/test_source_review_export.py
git commit -m "feat: export source policy selections"
```

## Task 5: Integrate Policy Reports Into Provider Baseline Replay

**Files:**
- Modify: `tests/test_provider_baseline_replay.py`
- Modify: `src/financial_report_llm_extractor/structured_sources/provider_baseline_replay.py`

- [ ] **Step 1: Write failing replay regression**

Add this test to `tests/test_provider_baseline_replay.py`:

```python
def test_provider_baseline_replay_reports_policy_selected_and_clean_counts(
    tmp_path: Path,
) -> None:
    result = write_provider_baseline_period_replay(
        inventory_path=Path(
            "tests/fixtures/provider_captures/provider_field_baseline/source_inventory.jsonl.gz"
        ),
        inventory_summary_path=Path(
            "tests/fixtures/provider_captures/provider_field_baseline/provider_field_inventory_summary.json"
        ),
        catalog_path=Path("field_catalog/turtle_v015_source_mapping_minimal.json"),
        output_dir=tmp_path / "baseline",
        company_ids=("600519", "00001"),
    )

    payload = json.loads(result.summary_path.read_text(encoding="utf-8"))
    companies = {company["company_id"]: company for company in payload["companies"]}

    maotai_combined = companies["600519"]["coverage"]["combined"]
    assert maotai_combined["selected_count"] >= maotai_combined["covered_count"]
    assert maotai_combined["clean_present_count"] <= maotai_combined["selected_count"]
    assert "revenue" in companies["600519"]["review"]["combined"][
        "selected_with_warnings_fields"
    ]

    hk_combined = companies["00001"]["review"]["combined"]
    assert set(hk_combined["selected_with_warnings_fields"]) >= {
        "total_assets",
        "total_cur_assets",
        "total_cur_liab",
        "total_liabilities",
    }
    assert "source_policy_report" in companies["00001"]["artifact_paths"]["combined"]
```

- [ ] **Step 2: Run focused test and verify it fails**

Run:

```bash
uv run pytest tests/test_provider_baseline_replay.py::test_provider_baseline_replay_reports_policy_selected_and_clean_counts -v
```

Expected: fail because provider replay does not build policy reports.

- [ ] **Step 3: Build and write policy reports per slice**

In `provider_baseline_replay.py`, import:

```python
from financial_report_llm_extractor.structured_sources.source_policy import (
    build_source_policy_report,
    write_source_policy_report,
)
```

Change `_write_slice()` signature:

```python
def _write_slice(
    output_dir: Path,
    *,
    catalog: Any,
    records: tuple[SourceInventoryRecord, ...],
    company_id: str,
    market: str,
) -> dict[str, Any]:
```

Inside `_write_slice()` after reconciliation:

```python
policy_report = build_source_policy_report(
    catalog,
    mapping,
    reconciliation,
    market=market,
    company_id=company_id,
)
export = build_source_first_export(
    mapping,
    reconciliation,
    profile="source_only",
    source_policy_report=policy_report,
)
write_source_policy_report(policy_report, output_dir / "source_policy_report.json")
```

Add artifact path:

```python
"source_policy_report": str(output_dir / "source_policy_report.json"),
```

Pass `company_id=company_id` and `market=company_groups["akshare"].market` from the three `_write_slice()` calls.

- [ ] **Step 4: Update coverage and review helpers**

If the branch already has `_export_coverage(export)` and `_review_lists(export)` from the provider replay review fix, extend those helpers in place. Do not recreate the older mapping/reconciliation-based helpers.

In `_export_coverage()`, keep existing keys and add:

```python
selected = sorted(
    field_id
    for field_id, item in export.items.items()
    if item.status == "present"
)
clean_present = sorted(
    field_id
    for field_id, item in export.items.items()
    if item.status == "present"
    and not item.warnings
    and not item.verification_required
)
return {
    "covered_fields": selected,
    "covered_count": len(selected),
    "selected_fields": selected,
    "selected_count": len(selected),
    "clean_present_fields": clean_present,
    "clean_present_count": len(clean_present),
    "total_fields": total,
    "coverage_ratio": len(selected) / total if total else 0.0,
}
```

In `_review_lists()`, add:

```python
"selected_with_warnings_fields": sorted(
    field_id
    for field_id, item in export.items.items()
    if item.status == "present" and (item.warnings or item.verification_required)
),
"fields_requiring_pdf_evidence": sorted(
    field_id
    for field_id, item in export.items.items()
    if item.verification_required or item.status == "needs_pdf_evidence"
),
```

Include those fields in Markdown after `conflict_fields`.

- [ ] **Step 5: Update existing provider replay conflict assertions**

In `tests/test_provider_baseline_replay.py`, update the existing `test_provider_baseline_replay_combined_uses_canonical_units_for_600519` assertions so they match the new policy-selected semantics. Replace the assertion that `revenue` and `net_profit` are both conflict fields with:

```python
assert "revenue" in combined_review["selected_with_warnings_fields"]
assert "net_profit" in combined_review["present_fields"]
assert "revenue" not in combined_review["conflict_fields"]
assert "net_profit" not in combined_review["conflict_fields"]
```

Update the existing reconciliation-report assertions too: `revenue` may still be a raw reconciliation conflict before policy selection, while `net_profit` should become `equivalent` after `PARENT_NETPROFIT` alias priority is corrected. Add a comment in the test explaining that raw reconciliation and export/review intentionally report different layers.

- [ ] **Step 6: Run provider replay tests**

Run:

```bash
uv run pytest tests/test_provider_baseline_replay.py -v
```

Expected: pass.

- [ ] **Step 7: Commit Task 5**

```bash
git add src/financial_report_llm_extractor/structured_sources/provider_baseline_replay.py tests/test_provider_baseline_replay.py
git commit -m "feat: replay provider baseline with source policy"
```

## Task 6: Verify Baseline Behavior And Documentation

**Files:**
- Modify: `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md`
- Modify: `docs/design/2026-05-01-structured-data-source-first-financial-extraction-design.md`
- Optional local artifacts: `tmp/runs/source_policy_conflict_resolution/`

- [ ] **Step 1: Run no-network replay into a review directory**

Run:

```bash
uv run financial-report-llm-extractor replay-provider-baseline \
  --inventory tests/fixtures/provider_captures/provider_field_baseline/source_inventory.jsonl.gz \
  --inventory-summary tests/fixtures/provider_captures/provider_field_baseline/provider_field_inventory_summary.json \
  --catalog field_catalog/turtle_v015_source_mapping_minimal.json \
  --out tmp/runs/source_policy_conflict_resolution
```

Expected output includes:

```text
companies=3
provider_baseline_replay_summary=tmp/runs/source_policy_conflict_resolution/provider_baseline_period_replay_summary.json
provider_baseline_replay_markdown=tmp/runs/source_policy_conflict_resolution/provider_baseline_period_replay_summary.md
```

- [ ] **Step 2: Inspect replay summary**

Run:

```bash
jq '.companies[] | {company_id, combined:.coverage.combined, review:.review.combined}' tmp/runs/source_policy_conflict_resolution/provider_baseline_period_replay_summary.json
```

Expected:

- `600519` combined has `selected_count >= 12`.
- `600519` review includes `revenue` in `selected_with_warnings_fields`.
- `00001` and `01113` combined review include HK balance-sheet totals in `selected_with_warnings_fields`.
- `source_policy_report.json` exists under each company slice.

- [ ] **Step 3: Update source-first design with the new layer**

In `docs/design/2026-05-01-structured-data-source-first-financial-extraction-design.md`, add a short subsection after cross-source reconciliation:

```markdown
### Source Policy Conflict Resolution

After canonical-unit reconciliation, remaining provider disagreements are routed through a deterministic source policy layer. The policy layer does not canonicalize facts. It classifies conflicts such as field semantic mismatch, FX-like ratio, suspected reporting-currency metadata, and single-source unverified coverage. When the catalog defines a market-specific primary source, the export may select that primary candidate while preserving warnings, cross-check candidates, and PDF verification requirements.
```

- [ ] **Step 4: Update roadmap**

In `docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md`, add source policy conflict resolution after canonical-unit reconciliation and before PDF/LLM fallback:

```markdown
-> cross-source reconciliation
-> source policy conflict classification and primary-candidate selection
-> selected PDF/LLM fallback
```

Add one guardrail bullet:

```markdown
- Cross-source conflicts must pass through source policy; primary-source selection must preserve warnings and verification requirements.
```

- [ ] **Step 5: Run focused and full verification**

Run:

```bash
uv run pytest tests/test_source_mapping_catalog.py tests/test_source_policy.py tests/test_source_review_export.py tests/test_provider_baseline_replay.py -v
uv run pytest -v
uv run ruff check .
uv run mypy src tests
git diff --check
```

Expected:

- Focused tests pass.
- Full tests pass.
- Ruff passes.
- Mypy passes.
- Diff check prints no output.

- [ ] **Step 6: Commit Task 6**

```bash
git add docs/design/2026-05-01-structured-data-source-first-financial-extraction-design.md docs/roadmap/2026-04-30-llm-first-financial-report-extractor-roadmap.md
git commit -m "docs: document source policy conflict layer"
```

## Plan Self-Review

- Spec coverage: Task 1 covers catalog policy metadata; Task 2 covers explicit field semantics; Task 3 covers conflict classification and source policy resolution; Task 4 covers export metadata; Task 5 covers provider baseline replay selected-vs-clean coverage; Task 6 covers roadmap/design updates and verification.
- Placeholder scan: no deferred implementation markers are used; every task has concrete files, test snippets, commands, and expected outcomes.
- Type consistency: `SourcePolicyReport`, `SourcePolicyItem`, `selection_status`, `verification_required`, and `conflict_classifications` are introduced before export and replay consume them.
- Verification: final task includes focused tests, full tests, ruff, mypy, and diff check.
