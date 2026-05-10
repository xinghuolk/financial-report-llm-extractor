"""Phase HK-C: industry_not_applicable catalog override + reason injection.

Per HK-coverage discovery: HK 01113 (CK Asset, real-estate) has no SGA
single-line by industry convention — neither AKShare nor Yahoo expose it,
and the PDF doesn't either. Currently this lands in `source_unavailable`
with reason `source_policy_resolvable`, which misleadingly implies "we
didn't try hard enough". The HK-C XS fix supplies a meaningful reason
without introducing a new bucket (deferred to a future phase if more
industry-NA cases accumulate, e.g. CN PAY_INTEREST_COMMISSION for
non-financial issuers).

Mechanism: catalog entry declares
    "industry_not_applicable": [
        {"market": "HK", "ticker": "01113", "reason": "..."}
    ]
and `classify_field`, when it would otherwise return `source_unavailable`,
overrides the reason to the catalog-supplied string when (market, ticker)
matches.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any


CATALOG_PATH = Path("field_catalog/turtle_v015_source_mapping_minimal.json")


def _make_export_item(
    field_id: str = "selling_general_administrative",
    *,
    status: str = "missing",
    selected_source: str | None = None,
) -> Any:
    from financial_report_llm_extractor.structured_sources.export import (
        SourceFirstExportItem,
    )
    return SourceFirstExportItem(
        field_id=field_id,
        status=status,  # type: ignore[arg-type]
        selected_source=selected_source,
        value=Decimal("100") if status == "present" else None,
        currency="CNY",
        unit="raw",
        conflict_classifications=(),
        review_notes=(),
    )


def _make_warning(category: str) -> Any:
    from financial_report_llm_extractor.structured_sources.warning_classification import (
        WarningClassificationItem,
    )
    return WarningClassificationItem(
        field_id="x",
        category=category,  # type: ignore[arg-type]
        status="missing",
        reasons=(),
        review_notes=(),
        warnings=(),
        selected_source=None,
        candidate_sources=(),
        verification_required=False,
    )


def test_hk_c_sga_catalog_has_industry_not_applicable_for_01113() -> None:
    """SGA entry must carry the industry_not_applicable spec for HK/01113."""
    doc = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    sga = doc["source_mappings"]["selling_general_administrative"]
    spec = sga.get("industry_not_applicable")
    assert isinstance(spec, list) and spec, (
        "SGA must declare industry_not_applicable list with at least one entry"
    )
    matches = [
        s for s in spec
        if s.get("market") == "HK" and s.get("ticker") == "01113"
    ]
    assert matches, "expected HK/01113 entry in SGA industry_not_applicable"
    assert matches[0].get("reason"), "industry_not_applicable entry must have reason"


def test_hk_c_catalog_entry_loads_industry_not_applicable() -> None:
    """Catalog loader must surface industry_not_applicable on SourceMappingEntry."""
    from financial_report_llm_extractor.structured_sources.catalog import (
        load_source_mapping_catalog,
    )

    cat = load_source_mapping_catalog(
        CATALOG_PATH, priorities=("P0", "P1", "P2", "P3"),
    )
    sga = cat.entries["selling_general_administrative"]
    spec = sga.industry_not_applicable  # type: ignore[attr-defined]
    assert isinstance(spec, tuple) and spec, (
        "industry_not_applicable must be a non-empty tuple after loading"
    )
    hk_01113 = [s for s in spec if s.market == "HK" and s.ticker == "01113"]
    assert hk_01113, "01113 HK SGA spec must be present"
    assert hk_01113[0].reason


def test_hk_c_classify_field_overrides_reason_when_industry_not_applicable() -> None:
    """When classify_field would return source_unavailable for a (market, ticker)
    that has an industry_not_applicable match, the bucket stays source_unavailable
    but the reason is replaced with the catalog-supplied string."""
    from financial_report_llm_extractor.structured_sources.catalog import (
        load_source_mapping_catalog,
    )
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        classify_field,
    )

    cat = load_source_mapping_catalog(
        CATALOG_PATH, priorities=("P0", "P1", "P2", "P3"),
    )
    sga = cat.entries["selling_general_administrative"]

    bucket, reason = classify_field(
        export_item=_make_export_item(),
        warning_item=_make_warning("source_unavailable"),
        mapping_entry=sga,
        pdf_provided=False,
        market="HK",
        company_id="01113",
    )

    assert bucket == "source_unavailable"
    assert reason is not None
    assert reason != "source_unavailable", (
        "reason must be overridden by industry_not_applicable spec, "
        f"got default reason {reason!r}"
    )


def test_hk_c_classify_field_no_override_for_non_matching_company() -> None:
    """A non-matching (market, ticker) gets the default source_unavailable reason."""
    from financial_report_llm_extractor.structured_sources.catalog import (
        load_source_mapping_catalog,
    )
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        classify_field,
    )

    cat = load_source_mapping_catalog(
        CATALOG_PATH, priorities=("P0", "P1", "P2", "P3"),
    )
    sga = cat.entries["selling_general_administrative"]

    bucket, reason = classify_field(
        export_item=_make_export_item(),
        warning_item=_make_warning("source_unavailable"),
        mapping_entry=sga,
        pdf_provided=False,
        market="CN",  # not HK/01113
        company_id="600519",
    )

    assert bucket == "source_unavailable"
    assert reason == "source_unavailable", (
        f"non-matching (market, ticker) must get default reason, got {reason!r}"
    )


def test_hk_c_classify_field_does_not_override_other_buckets() -> None:
    """If classify_field would return clean_present, the override must NOT
    apply — industry_not_applicable only refines the reason of
    `source_unavailable` rows. Otherwise we'd corrupt good data."""
    from financial_report_llm_extractor.structured_sources.catalog import (
        load_source_mapping_catalog,
    )
    from financial_report_llm_extractor.structured_sources.company_evaluation import (
        classify_field,
    )

    cat = load_source_mapping_catalog(
        CATALOG_PATH, priorities=("P0", "P1", "P2", "P3"),
    )
    sga = cat.entries["selling_general_administrative"]

    bucket, reason = classify_field(
        export_item=_make_export_item(status="present", selected_source="yahoo"),
        warning_item=None,
        mapping_entry=sga,
        pdf_provided=False,
        market="HK",
        company_id="01113",
    )

    assert bucket == "clean_present"
    assert reason is None
