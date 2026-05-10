"""Phase H2.4: surgical fixes for the 3 cumulative-review findings.

#1 — derivation must be market-scoped. CN SGA derivation
    `akshare:MANAGE_EXPENSE + akshare:SALE_EXPENSE` must NOT be attempted
    when running against HK records (would always block since AKShare HK
    lacks those raw fields).

#2 — provider-raw derivation operands must go through normalize_money().
    Today `_resolve_derivation_operand` sets value AND normalized_value
    both to `parsed_numeric_value`, which silently drops unit_multiplier.
    Latent bug: any future provider raw operand in 千元/million scales
    would emit a wrong normalized_value.

#3 — derived clean_present rows must surface a selected_source.
    Today CN SGA exports as bucket=clean_present + value=14,954,950,119.87
    + selected_source=null (because source_policy returns
    selected_single_source without a selected_candidate). Should expose
    "akshare" so reviewers can audit the derivation provider.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from financial_report_llm_extractor.structured_sources.catalog import (
    load_source_mapping_catalog,
)
from financial_report_llm_extractor.structured_sources.mapping import (
    map_source_inventory,
)
from financial_report_llm_extractor.structured_sources.models import (
    SourceEvidence,
    SourceInventoryRecord,
)


CATALOG_PATH = Path("field_catalog/turtle_v015_source_mapping_minimal.json")


def _hydrate_record(d: dict[str, Any]) -> SourceInventoryRecord:
    evs = tuple(SourceEvidence(**e) for e in d.get("source_evidence", []))
    pnv = d.get("parsed_numeric_value")
    parsed = Decimal(str(pnv)) if pnv is not None else None
    return SourceInventoryRecord(
        ticker=d["ticker"],
        market=d["market"],
        source=d["source"],
        statement_type=d["statement_type"],
        report_type=d.get("report_type"),
        period=d.get("period"),
        fiscal_year=d.get("fiscal_year"),
        account_standard=d.get("account_standard"),
        scope=d.get("scope", "unknown"),
        raw_field_code=d.get("raw_field_code"),
        raw_field_name=d.get("raw_field_name") or "",
        raw_value=d.get("raw_value"),
        parsed_numeric_value=parsed,
        currency=cast(Any, d.get("currency", "unknown")),
        unit=d.get("unit"),
        value_type=d.get("value_type", "money"),
        source_status=d.get("source_status", "present"),
        source_evidence=evs,
    )


def _make_record(
    *,
    ticker: str,
    market: str,
    raw_field_name: str,
    raw_value: float,
    unit: str = "yuan",
    currency: str = "CNY",
    statement_type: str = "income_statement",
) -> SourceInventoryRecord:
    return SourceInventoryRecord(
        ticker=ticker,
        market=market,
        source="akshare",
        statement_type=statement_type,
        report_type="annual",
        period="2024-12-31",
        fiscal_year=None,
        account_standard=None,
        scope="consolidated",
        raw_field_code=raw_field_name,
        raw_field_name=raw_field_name,
        raw_value=raw_value,
        parsed_numeric_value=Decimal(str(raw_value)),
        currency=cast(Any, currency),
        unit=unit,
        value_type="money",
        source_status="present",
        source_evidence=(
            SourceEvidence(
                source="akshare",
                adapter="akshare",
                function="test",
                artifact_id=f"test_{ticker}_{statement_type}",
                provider_version=None,
                raw_record_id=f"{ticker}:{raw_field_name}",
                raw_field_code=raw_field_name,
                raw_field_name=raw_field_name,
                retrieved_at=None,
            ),
        ),
    )


# ---------- Finding 1: market-scoped derivation ----------


def test_h2_4_finding1_hk_sga_does_not_get_blocked_by_cn_derivation() -> None:
    """When mapping HK records, the CN-only SGA derivation must NOT run.
    Pre-H2.4: 01113 SGA returns status=blocked with errors:
        derivation input not present: akshare:MANAGE_EXPENSE
        derivation input not present: akshare:SALE_EXPENSE
    Post-H2.4: status=missing (no derivation attempted)."""
    cat = load_source_mapping_catalog(
        CATALOG_PATH, priorities=("P0", "P1", "P2", "P3"),
    )
    inventory_path = Path("tmp/runs/h2_2_after/01113/source_inventory.jsonl")
    if not inventory_path.exists():
        pytest.skip(f"HK 01113 inventory fixture missing at {inventory_path}")
    records = []
    with open(inventory_path) as f:
        for line in f:
            records.append(_hydrate_record(json.loads(line)))
    result = map_source_inventory(catalog=cat, records=records)
    sga = result.fields["selling_general_administrative"]

    # Forbidden outcome: blocked + CN-derivation-input errors.
    is_blocked_by_cn_derivation = sga.status == "blocked" and any(
        "akshare:MANAGE_EXPENSE" in e or "akshare:SALE_EXPENSE" in e
        for e in sga.errors
    )
    assert not is_blocked_by_cn_derivation, (
        f"HK SGA must not be blocked by CN-only derivation. "
        f"status={sga.status!r} errors={sga.errors!r}"
    )


def test_h2_4_finding1_cn_sga_derivation_still_works() -> None:
    """Regression guard: CN derivation still runs and produces the SGA value
    for 600519 (otherwise we've over-corrected)."""
    cat = load_source_mapping_catalog(
        CATALOG_PATH, priorities=("P0", "P1", "P2", "P3"),
    )
    inventory_path = Path("tmp/runs/600519_2024-12-31/source_inventory.jsonl")
    if not inventory_path.exists():
        pytest.skip(f"CN 600519 inventory fixture missing at {inventory_path}")
    records = []
    with open(inventory_path) as f:
        for line in f:
            records.append(_hydrate_record(json.loads(line)))
    result = map_source_inventory(catalog=cat, records=records)
    sga = result.fields["selling_general_administrative"]
    assert sga.status in ("derived", "present"), (
        f"CN SGA derivation regression: expected derived/present, "
        f"got status={sga.status!r} errors={sga.errors!r}"
    )
    # Sample-verified: MANAGE+SALE = 14,954,950,119.87
    assert sga.normalized_value == Decimal("14954950119.87"), (
        f"CN SGA derived value drift: expected 14954950119.87, "
        f"got {sga.normalized_value}"
    )


# ---------- Finding 2: derivation operand normalization ----------


def test_h2_4_finding2_derivation_operand_respects_unit_multiplier() -> None:
    """Construct synthetic CN AKShare records in 千元 (multiplier 1000) and
    feed through SGA derivation. Expected normalized_value = sum * 1000.

    Pre-H2.4: returns sum * 1 (raw parsed_numeric_value used as both value
    and normalized_value, dropping unit_multiplier).
    Post-H2.4: returns sum * 1000.
    """
    cat = load_source_mapping_catalog(
        CATALOG_PATH, priorities=("P0", "P1", "P2", "P3"),
    )
    records = (
        _make_record(
            ticker="TEST",
            market="CN",
            raw_field_name="MANAGE_EXPENSE",
            raw_value=1000.0,  # 1000 千元
            unit="千元",
        ),
        _make_record(
            ticker="TEST",
            market="CN",
            raw_field_name="SALE_EXPENSE",
            raw_value=2000.0,  # 2000 千元
            unit="千元",
        ),
    )
    result = map_source_inventory(catalog=cat, records=records)
    sga = result.fields["selling_general_administrative"]
    assert sga.status == "derived", (
        f"expected derived status, got {sga.status!r} errors={sga.errors!r}"
    )
    # Raw sum = 3000; 千元 multiplier = 1000; normalized = 3,000,000.
    assert sga.normalized_value == Decimal("3000000"), (
        f"千元 unit_multiplier dropped — got normalized={sga.normalized_value}, "
        f"expected 3000000 (3000 千元 * 1000)"
    )


# ---------- Finding 3: selected_source for derived ----------


def test_h2_4_finding3_cn_derived_sga_export_carries_selected_source() -> None:
    """End-to-end: CN 600519 SGA full pipeline → export must report
    selected_source='akshare' for the derived clean_present row."""
    from financial_report_llm_extractor.structured_sources.export import (
        build_source_first_export,
    )
    from financial_report_llm_extractor.structured_sources.reconciliation import (
        reconcile_mapped_fields,
    )
    from financial_report_llm_extractor.structured_sources.source_policy import (
        build_source_policy_report,
    )

    cat = load_source_mapping_catalog(
        CATALOG_PATH, priorities=("P0", "P1", "P2", "P3"),
    )
    inventory_path = Path("tmp/runs/600519_2024-12-31/source_inventory.jsonl")
    if not inventory_path.exists():
        pytest.skip(f"CN 600519 inventory fixture missing at {inventory_path}")
    records = []
    with open(inventory_path) as f:
        for line in f:
            records.append(_hydrate_record(json.loads(line)))
    mapping = map_source_inventory(catalog=cat, records=records)
    reconciliation = reconcile_mapped_fields(mapping)
    policy = build_source_policy_report(
        catalog=cat,
        mapping=mapping,
        reconciliation=reconciliation,
        market="CN",
        company_id="600519",
    )
    export = build_source_first_export(
        mapping_result=mapping,
        reconciliation_report=reconciliation,
        profile="source_only",
        source_policy_report=policy,
    )
    sga = export.items["selling_general_administrative"]
    assert sga.status == "present", (
        f"SGA must be present for CN 600519, got status={sga.status!r}"
    )
    assert sga.selected_source == "akshare", (
        f"Derived CN SGA export must carry selected_source='akshare', "
        f"got {sga.selected_source!r}"
    )
