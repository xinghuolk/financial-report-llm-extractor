from decimal import Decimal
from typing import Any, cast

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
from financial_report_llm_extractor.structured_sources.hk_yahoo_trust_policy import (
    HkYahooTrustPolicy,
    HkYahooTrustRule,
    HkYahooTrustSample,
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


def test_source_policy_requires_related_value_match_for_semantic_mismatch() -> None:
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
                normalized_value=Decimal("100"),
                currency="CNY",
            ),
            _candidate(
                source="yahoo",
                raw_field_name="Total Revenue",
                raw_field_code=None,
                normalized_value=Decimal("101"),
                currency="CNY",
            ),
        ),
        policy_evidence_candidates=(
            _candidate(
                source="akshare",
                raw_field_name="营业总收入",
                raw_field_code="TOTAL_OPERATE_INCOME",
                normalized_value=Decimal("102"),
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
    assert item.conflict_classifications == ("normalized_value_conflict",)


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
            "total_assets": _field(
                "total_assets",
                Decimal("100"),
                Decimal("110.71499745"),
            ),
            "total_cur_assets": _field(
                "total_cur_assets",
                Decimal("50"),
                Decimal("55.357498725"),
            ),
            "total_liabilities": _field(
                "total_liabilities",
                Decimal("20"),
                Decimal("22.14299949"),
            ),
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


def test_source_policy_ignores_fx_like_ratio_when_cross_check_values_are_zero() -> None:
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
            "total_assets": _field("total_assets", Decimal("100"), Decimal("0")),
            "total_cur_assets": _field("total_cur_assets", Decimal("50"), Decimal("0")),
            "total_liabilities": _field(
                "total_liabilities",
                Decimal("20"),
                Decimal("0"),
            ),
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

    item = report.items["total_assets"]
    assert item.selection_status == "selected_primary"
    assert item.conflict_classifications == ("normalized_value_conflict",)


def test_source_policy_requires_hk_akshare_statement_metadata_proof() -> None:
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
            "total_assets": _field(
                "total_assets",
                Decimal("100"),
                Decimal("110.71499745"),
                akshare_statement_metadata_proven=False,
            ),
            "total_cur_assets": _field(
                "total_cur_assets",
                Decimal("50"),
                Decimal("55.357498725"),
                akshare_statement_metadata_proven=False,
            ),
            "total_liabilities": _field(
                "total_liabilities",
                Decimal("20"),
                Decimal("22.14299949"),
                akshare_statement_metadata_proven=False,
            ),
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

    item = report.items["total_assets"]
    assert item.selection_status == "unresolved_conflict"
    assert item.selected_candidate is None
    assert item.verification_required is True
    assert item.conflict_classifications == (
        "fx_like_ratio",
        "metadata_currency_suspected",
        "statement_metadata_unproven",
    )


def test_source_policy_requires_hk_primary_statement_metadata_proof_for_yahoo() -> None:
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
                            primary_route="yahoo_direct",
                            cross_check_routes=("akshare_direct",),
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
            "total_assets": _field(
                "total_assets",
                Decimal("100"),
                Decimal("110.71499745"),
            ),
            "total_cur_assets": _field(
                "total_cur_assets",
                Decimal("50"),
                Decimal("55.357498725"),
            ),
            "total_liabilities": _field(
                "total_liabilities",
                Decimal("20"),
                Decimal("22.14299949"),
            ),
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

    item = report.items["total_assets"]
    assert item.selection_status == "unresolved_conflict"
    assert item.selected_candidate is None
    assert item.verification_required is True
    assert item.conflict_classifications == (
        "fx_like_ratio",
        "metadata_currency_suspected",
        "statement_metadata_unproven",
    )


def test_source_policy_blocks_hk_single_source_currency_as_unit() -> None:
    catalog = _catalog(
        "total_assets",
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
    mapping = TurtleMappingResult(
        catalog_id="test",
        catalog_version="1",
        fields={
            "total_assets": MappedTurtleField(
                field_id="total_assets",
                status="present",
                value=Decimal("100"),
                normalized_value=Decimal("100"),
                currency="HKD",
                unit="HKD",
                canonical_unit="HKD",
                period="2025-12-31",
                candidates=(
                    _candidate(
                        source="akshare",
                        raw_field_name="总资产",
                        raw_field_code="TOTAL_ASSETS",
                        normalized_value=Decimal("100"),
                        currency="HKD",
                        unit="HKD",
                        statement_metadata_proven=False,
                    ),
                ),
            )
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

    item = report.items["total_assets"]
    assert item.selection_status == "unresolved_conflict"
    assert item.selected_candidate is None
    assert item.verification_required is True
    assert "currency_as_unit" in item.conflict_classifications
    assert "statement_metadata_unproven" in item.conflict_classifications


def test_source_policy_allows_hk_yahoo_primary_when_statement_metadata_is_proven() -> None:
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
                            primary_route="yahoo_direct",
                            cross_check_routes=("akshare_direct",),
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
            "total_assets": _field(
                "total_assets",
                Decimal("100"),
                Decimal("110.71499745"),
                yahoo_statement_metadata_proven=True,
            ),
            "total_cur_assets": _field(
                "total_cur_assets",
                Decimal("50"),
                Decimal("55.357498725"),
                yahoo_statement_metadata_proven=True,
            ),
            "total_liabilities": _field(
                "total_liabilities",
                Decimal("20"),
                Decimal("22.14299949"),
                yahoo_statement_metadata_proven=True,
            ),
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

    item = report.items["total_assets"]
    assert item.selection_status == "selected_primary"
    assert item.selected_candidate is not None
    assert item.selected_candidate.source == "yahoo"
    assert item.verification_required is True
    assert item.conflict_classifications == (
        "fx_like_ratio",
        "metadata_currency_suspected",
    )


def test_source_policy_marks_hk_yahoo_verified_field_clean_with_trust_policy() -> None:
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
                            primary_route="yahoo_direct",
                            cross_check_routes=("akshare_direct",),
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
            "total_assets": _field(
                "total_assets",
                Decimal("100"),
                Decimal("110.71499745"),
                yahoo_statement_metadata_proven=False,
            ),
            "total_cur_assets": _field(
                "total_cur_assets",
                Decimal("50"),
                Decimal("55.357498725"),
                yahoo_statement_metadata_proven=False,
                yahoo_raw_field_name="Current Assets",
            ),
            "total_liabilities": _field(
                "total_liabilities",
                Decimal("20"),
                Decimal("22.14299949"),
                yahoo_statement_metadata_proven=False,
                yahoo_raw_field_name="Total Liabilities Net Minority Interest",
            ),
        },
    )
    reconciliation = reconcile_mapped_fields(mapping)

    report = build_source_policy_report(
        catalog,
        mapping,
        reconciliation,
        market="HK",
        company_id="00001",
        hk_yahoo_trust_policy=_trust_policy(),
    )

    item = report.items["total_assets"]
    assert item.selection_status == "selected_primary"
    assert item.selected_candidate is not None
    assert item.selected_candidate.source == "yahoo"
    assert item.verification_required is False
    assert item.conflict_classifications == ()
    assert item.warnings == ()
    assert item.trust_policy_evidence is not None
    assert item.trust_policy_evidence["policy_id"] == (
        "hk_yahoo_raw_hkd_pdf_verified:total_assets"
    )


def test_source_policy_does_not_apply_policy_without_raw_field_match() -> None:
    catalog = _catalog(
        "total_assets",
        SourcePolicy(
            semantic_concept="reported statement line",
            market_policies={
                "HK": MarketSourcePolicy(
                    primary_route="yahoo_direct",
                    cross_check_routes=("akshare_direct",),
                    on_conflict="select_primary_require_pdf",
                )
            },
            verification_requirement="pdf_required_on_conflict",
        ),
    )
    mapping = _mapping(
        "total_assets",
        (
            _candidate(
                "akshare",
                "总资产",
                "TOTAL_ASSETS",
                Decimal("100"),
                currency="HKD",
                unit="raw",
                canonical_unit="HKD",
                statement_metadata_proven=True,
            ),
            _candidate(
                "yahoo",
                "Total Liabilities Net Minority Interest",
                None,
                Decimal("100"),
                currency="HKD",
                unit="raw",
                canonical_unit="HKD",
                unit_multiplier=Decimal("1"),
            ),
        ),
        policy_evidence_candidates=(),
    )
    reconciliation = reconcile_mapped_fields(mapping)

    report = build_source_policy_report(
        catalog,
        mapping,
        reconciliation,
        market="HK",
        company_id="00001",
        hk_yahoo_trust_policy=_trust_policy(),
    )

    item = report.items["total_assets"]
    assert item.verification_required is True
    assert item.trust_policy_evidence is None
    assert item.conflict_classifications == ("statement_metadata_unproven",)


def test_source_policy_keeps_gross_profit_verification_required_without_definition_proof() -> None:
    catalog = _catalog(
        "gross_profit",
        SourcePolicy(
            semantic_concept="reported statement line",
            market_policies={
                "HK": MarketSourcePolicy(
                    primary_route="yahoo_direct",
                    cross_check_routes=("akshare_direct",),
                    on_conflict="select_primary_require_pdf",
                )
            },
            verification_requirement="pdf_required_on_conflict",
        ),
    )
    mapping = _mapping(
        "gross_profit",
        (
            _candidate(
                "akshare",
                "毛利",
                "GROSS_PROFIT",
                Decimal("100"),
                currency="HKD",
                unit="raw",
                canonical_unit="HKD",
                statement_metadata_proven=True,
            ),
            _candidate(
                "yahoo",
                "Gross Profit",
                None,
                Decimal("100"),
                currency="HKD",
                unit="raw",
                canonical_unit="HKD",
                unit_multiplier=Decimal("1"),
            ),
        ),
        policy_evidence_candidates=(),
    )
    reconciliation = reconcile_mapped_fields(mapping)

    report = build_source_policy_report(
        catalog,
        mapping,
        reconciliation,
        market="HK",
        company_id="00001",
        hk_yahoo_trust_policy=_trust_policy(),
    )

    item = report.items["gross_profit"]
    assert item.verification_required is True
    assert item.trust_policy_evidence is None
    assert item.conflict_classifications == ("statement_metadata_unproven",)


def test_source_policy_report_serializes_trust_policy_evidence_separately() -> None:
    catalog = _catalog(
        "total_assets",
        SourcePolicy(
            semantic_concept="reported statement line",
            market_policies={
                "HK": MarketSourcePolicy(
                    primary_route="yahoo_direct",
                    cross_check_routes=("akshare_direct",),
                    on_conflict="select_primary_require_pdf",
                )
            },
            verification_requirement="pdf_required_on_conflict",
        ),
    )
    mapping = _mapping(
        "total_assets",
        (
            _candidate(
                "akshare",
                "总资产",
                "TOTAL_ASSETS",
                Decimal("100"),
                currency="HKD",
                unit="raw",
                canonical_unit="HKD",
                statement_metadata_proven=True,
            ),
            _candidate(
                "yahoo",
                "Total Assets",
                None,
                Decimal("100"),
                currency="HKD",
                unit="raw",
                canonical_unit="HKD",
                unit_multiplier=Decimal("1"),
            ),
        ),
        policy_evidence_candidates=(),
    )
    reconciliation = reconcile_mapped_fields(mapping)

    report = build_source_policy_report(
        catalog,
        mapping,
        reconciliation,
        market="HK",
        company_id="00001",
        hk_yahoo_trust_policy=_trust_policy(),
    )
    item_payload = cast(dict[str, Any], report.to_dict()["items"])["total_assets"]
    item_payload = cast(dict[str, Any], item_payload)

    trust_policy_evidence = cast(dict[str, Any], item_payload["trust_policy_evidence"])
    selected_candidate = cast(dict[str, Any], item_payload["selected_candidate"])
    assert trust_policy_evidence["policy_id"] == (
        "hk_yahoo_raw_hkd_pdf_verified:total_assets"
    )
    assert selected_candidate["source_evidence"]


def test_source_policy_does_not_classify_fx_like_ratio_across_periods() -> None:
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
            "total_assets": _field(
                "total_assets",
                Decimal("100"),
                Decimal("110.71499745"),
                period="2025-12-31",
            ),
            "total_cur_assets": _field(
                "total_cur_assets",
                Decimal("50"),
                Decimal("55.357498725"),
                period="2024-12-31",
            ),
            "total_liabilities": _field(
                "total_liabilities",
                Decimal("20"),
                Decimal("22.14299949"),
                period="2023-12-31",
            ),
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

    item = report.items["total_assets"]
    assert item.selection_status == "selected_primary"
    assert item.conflict_classifications == ("normalized_value_conflict",)


def test_source_policy_does_not_select_primary_without_currency_metadata() -> None:
    catalog = _catalog(
        "revenue",
        SourcePolicy(
            semantic_concept="operating revenue",
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
                normalized_value=Decimal("100"),
                currency="unknown",
                unit=None,
                canonical_unit=None,
            ),
            _candidate(
                source="yahoo",
                raw_field_name="Total Revenue",
                raw_field_code=None,
                normalized_value=Decimal("101"),
                currency="CNY",
            ),
        ),
        policy_evidence_candidates=(),
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
    assert item.selection_status == "unresolved_conflict"
    assert item.selected_candidate is None
    assert item.verification_required is True
    assert item.conflict_classifications == (
        "normalized_value_conflict",
        "currency_metadata_required",
    )


def test_source_policy_does_not_select_inventory_order_fallback_when_primary_missing() -> None:
    catalog = _catalog(
        "revenue",
        SourcePolicy(
            semantic_concept="operating revenue",
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
                source="yahoo",
                raw_field_name="Total Revenue",
                raw_field_code=None,
                normalized_value=Decimal("100"),
                currency="CNY",
            ),
            _candidate(
                source="fixture",
                raw_field_name="Revenue",
                raw_field_code=None,
                normalized_value=Decimal("100"),
                currency="CNY",
            ),
        ),
        policy_evidence_candidates=(),
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
    assert item.selection_status == "unresolved_conflict"
    assert item.selected_candidate is None
    assert item.verification_required is True
    assert item.conflict_classifications == ("missing_source_candidate",)


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
    *,
    policy_evidence_candidates: tuple[TurtleMappingCandidate, ...] | None = None,
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
                if policy_evidence_candidates is None and field_id == "revenue"
                else policy_evidence_candidates or (),
                errors=("multiple source candidates matched catalog aliases",),
            )
        },
    )


def _field(
    field_id: str,
    akshare_value: Decimal,
    yahoo_value: Decimal,
    *,
    akshare_statement_metadata_proven: bool = True,
    yahoo_statement_metadata_proven: bool = False,
    yahoo_raw_field_name: str = "Total Assets",
    period: str = "2025-12-31",
) -> MappedTurtleField:
    return MappedTurtleField(
        field_id=field_id,
        status="ambiguous",
        candidates=(
            _candidate(
                "akshare",
                "总资产",
                "TOTAL_ASSETS",
                akshare_value,
                currency="HKD",
                unit="raw",
                statement_metadata_proven=akshare_statement_metadata_proven,
                period=period,
            ),
            _candidate(
                "yahoo",
                yahoo_raw_field_name,
                None,
                yahoo_value,
                currency="HKD",
                period=period,
                statement_metadata_proven=yahoo_statement_metadata_proven,
                unit_multiplier=Decimal("1"),
            ),
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
    unit: str | None = "default",
    canonical_unit: str | None = "default",
    statement_metadata_proven: bool = False,
    unit_multiplier: Decimal | None = None,
    period: str = "2025-12-31",
) -> TurtleMappingCandidate:
    resolved_unit = "raw" if unit == "default" and source == "yahoo" else unit
    if resolved_unit == "default":
        resolved_unit = currency
    resolved_canonical_unit = currency if canonical_unit == "default" else canonical_unit
    return TurtleMappingCandidate(
        source=source,  # type: ignore[arg-type]
        raw_field_name=raw_field_name,
        raw_field_code=raw_field_code,
        raw_value=str(normalized_value),
        value=normalized_value,
        normalized_value=normalized_value,
        currency=currency,  # type: ignore[arg-type]
        unit=resolved_unit,
        canonical_unit=resolved_canonical_unit,  # type: ignore[arg-type]
        statement_metadata_proven=statement_metadata_proven,
        unit_multiplier=unit_multiplier,
        period=period,
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


def _trust_policy() -> HkYahooTrustPolicy:
    return HkYahooTrustPolicy(
        version=1,
        market="HK",
        provider="yahoo",
        rules=(
            _trust_rule("total_assets", "Total Assets", "yahoo_pdf_verified"),
            _trust_rule("total_cur_assets", "Current Assets", "yahoo_pdf_verified"),
            _trust_rule(
                "total_liabilities",
                "Total Liabilities Net Minority Interest",
                "yahoo_pdf_verified",
            ),
            _trust_rule("gross_profit", "Gross Profit", "yahoo_definition_unverified"),
        ),
    )


def _trust_rule(
    field_id: str,
    raw_field_name: str,
    classification: str,
) -> HkYahooTrustRule:
    return HkYahooTrustRule(
        policy_id=f"hk_yahoo_raw_hkd_pdf_verified:{field_id}",
        field_id=field_id,
        classification=classification,  # type: ignore[arg-type]
        trusted_currency="HKD",
        trusted_unit="raw",
        trusted_unit_multiplier=Decimal("1"),
        allowed_yahoo_raw_fields=(raw_field_name,),
        samples=(
            (_trust_sample(field_id, raw_field_name),)
            if classification == "yahoo_pdf_verified"
            else ()
        ),
    )


def _trust_sample(field_id: str, raw_field_name: str) -> HkYahooTrustSample:
    return HkYahooTrustSample(
        company_id="00001",
        provider_ticker="0001.HK",
        report_ref="annual.pdf",
        pdf_page=1,
        statement_name="Consolidated Statement",
        statement_line=field_id,
        reported_currency="HKD",
        reported_unit="million",
        pdf_value="1",
        pdf_unit_multiplier=Decimal("1000000"),
        expected_yahoo_raw_value="1000000",
        yahoo_raw_field=raw_field_name,
        match_basis="fixture arithmetic",
    )
