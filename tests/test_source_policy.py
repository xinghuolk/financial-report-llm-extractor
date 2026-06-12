from decimal import Decimal
from pathlib import Path
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
from financial_report_llm_extractor.structured_sources.provider_semantics import (
    ProviderSemanticsCatalog,
    load_provider_semantics_catalog,
)
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
        provider_semantics_catalog=_provider_semantics(),
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


def test_source_policy_requires_provider_semantics_catalog_for_hk_yahoo_trust() -> None:
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
        provider_semantics_catalog=None,
    )

    item = report.items["total_assets"]
    assert item.verification_required is True
    assert item.trust_policy_evidence is None
    assert item.conflict_classifications == ("statement_metadata_unproven",)


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
        provider_semantics_catalog=_provider_semantics(),
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
        provider_semantics_catalog=_provider_semantics(),
    )

    item = report.items["gross_profit"]
    assert item.verification_required is True
    assert item.trust_policy_evidence is None
    assert item.conflict_classifications == ("statement_metadata_unproven",)


def test_source_policy_trusts_hk_net_profit_provider_semantics_primary() -> None:
    catalog = _catalog(
        "net_profit",
        SourcePolicy(
            semantic_concept="profit attributable to ordinary/common shareholders",
            market_policies={
                "HK": MarketSourcePolicy(
                    primary_route="yahoo_direct",
                    cross_check_routes=("akshare_direct",),
                    on_conflict="select_primary_require_pdf",
                    single_source_requires_pdf=True,
                )
            },
            verification_requirement="pdf_required_on_conflict",
        ),
    )
    mapping = _mapping(
        "net_profit",
        (
            _candidate(
                "yahoo",
                "Net Income Common Stockholders",
                None,
                Decimal("11841000000"),
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
        provider_semantics_catalog=_provider_semantics(),
    )

    item = report.items["net_profit"]
    assert item.selection_status == "selected_primary"
    assert item.verification_required is False
    assert item.conflict_classifications == ()
    assert item.trust_policy_evidence is not None
    assert item.trust_policy_evidence["field_id"] == "net_profit"


def test_source_policy_rejects_hk_net_profit_related_yahoo_raw_field() -> None:
    catalog = _catalog(
        "net_profit",
        SourcePolicy(
            semantic_concept="profit attributable to ordinary/common shareholders",
            market_policies={
                "HK": MarketSourcePolicy(
                    primary_route="yahoo_direct",
                    cross_check_routes=("akshare_direct",),
                    on_conflict="select_primary_require_pdf",
                    single_source_requires_pdf=True,
                )
            },
            verification_requirement="pdf_required_on_conflict",
        ),
    )
    mapping = _mapping(
        "net_profit",
        (
            _candidate(
                "yahoo",
                "Net Income",
                None,
                Decimal("11841000000"),
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
        hk_yahoo_trust_policy=_trust_policy_with_net_income_related_field(),
        provider_semantics_catalog=_provider_semantics(),
    )

    item = report.items["net_profit"]
    assert item.selection_status == "unresolved_conflict"
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
        provider_semantics_catalog=_provider_semantics(),
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


def _single_source_mapping(
    field_id: str,
    candidate: TurtleMappingCandidate,
) -> TurtleMappingResult:
    """A status='present' mapping with exactly one candidate — routes into
    `_resolve_single_source` (the `_mapping` helper's status='ambiguous'
    models the multi-candidate conflict path instead)."""
    return TurtleMappingResult(
        catalog_id="test",
        catalog_version="1",
        fields={
            field_id: MappedTurtleField(
                field_id=field_id,
                status="present",
                candidates=(candidate,),
                errors=(),
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
            _trust_rule(
                "net_profit",
                "Net Income Common Stockholders",
                "yahoo_pdf_verified",
            ),
            _trust_rule("gross_profit", "Gross Profit", "yahoo_definition_unverified"),
        ),
    )


def _trust_policy_with_net_income_related_field() -> HkYahooTrustPolicy:
    return HkYahooTrustPolicy(
        version=1,
        market="HK",
        provider="yahoo",
        rules=(
            _trust_rule("net_profit", "Net Income", "yahoo_pdf_verified"),
        ),
    )


def _provider_semantics() -> ProviderSemanticsCatalog:
    return load_provider_semantics_catalog(
        Path("field_catalog/provider_raw_semantics_hk.json")
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


def test_source_policy_emits_clean_for_derived_field_without_candidates() -> None:
    """Phase H2.1 follow-up: when a field's mapping result has status='derived'
    AND no per-source candidates (because `_derive_field` resolved operands
    directly from records via `provider:RAW` syntax), source_policy must emit
    `selected_single_source` so the field carries to clean_present.

    Without this branch, _resolve_field would treat the empty candidates list
    as 'no primary candidate' and mis-classify as unresolved_conflict, masking
    the derivation result.
    """
    catalog = _catalog(
        "selling_general_administrative",
        SourcePolicy(
            semantic_concept="selling general and administrative expenses",
            market_policies={
                "CN": MarketSourcePolicy(
                    primary_route="akshare_direct",
                    cross_check_routes=(),
                    on_conflict="select_primary",
                )
            },
        ),
    )
    derived_mapping = TurtleMappingResult(
        catalog_id="test",
        catalog_version="1",
        fields={
            "selling_general_administrative": MappedTurtleField(
                field_id="selling_general_administrative",
                status="derived",
                value=Decimal("14954950119.87"),
                normalized_value=Decimal("14954950119.87"),
                currency="CNY",
                unit="yuan",
                canonical_unit="CNY",
                # No candidates: derivation built the value from raw records.
                candidates=(),
                derived_from=("akshare:MANAGE_EXPENSE", "akshare:SALE_EXPENSE"),
            )
        },
    )
    reconciliation = reconcile_mapped_fields(derived_mapping)

    report = build_source_policy_report(
        catalog,
        derived_mapping,
        reconciliation,
        market="CN",
        company_id="600519",
    )

    item = report.items["selling_general_administrative"]
    assert item.selection_status == "selected_single_source"
    assert item.conflict_classifications == ()
    assert item.verification_required is False


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


def test_source_policy_standardized_branch_requires_matching_trust_rule() -> None:
    """select_primary_standardized must NOT fire on the catalog flag alone:
    without a paired yahoo_standardized_accepted trust rule the conflict
    falls through to normal handling (2026-06-12 review hardening)."""
    catalog = _catalog(
        "gross_profit",
        SourcePolicy(
            semantic_concept="reported statement line",
            market_policies={
                "HK": MarketSourcePolicy(
                    primary_route="yahoo_direct",
                    cross_check_routes=("akshare_direct",),
                    on_conflict="select_primary_standardized",
                    single_source_requires_pdf=False,
                )
            },
        ),
    )
    mapping = _mapping(
        "gross_profit",
        (
            _candidate(
                "akshare",
                "毛利",
                "GROSS_PROFIT",
                Decimal("200"),
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

    # default _trust_policy() carries gross_profit as
    # yahoo_definition_unverified — NOT yahoo_standardized_accepted.
    report = build_source_policy_report(
        catalog,
        mapping,
        reconciliation,
        market="HK",
        company_id="00001",
        hk_yahoo_trust_policy=_trust_policy(),
        provider_semantics_catalog=_provider_semantics(),
    )

    item = report.items["gross_profit"]
    assert item.verification_required is True
    assert item.selection_status != "selected_primary"


def test_source_policy_standardized_branch_rejects_unaccepted_currency() -> None:
    """The standardized acceptance honors the trust rule's currency gate:
    a candidate outside accepted_currencies() falls through to normal
    conflict handling instead of landing clean (2026-06-12 review)."""
    catalog = _catalog(
        "gross_profit",
        SourcePolicy(
            semantic_concept="reported statement line",
            market_policies={
                "HK": MarketSourcePolicy(
                    primary_route="yahoo_direct",
                    cross_check_routes=("akshare_direct",),
                    on_conflict="select_primary_standardized",
                    single_source_requires_pdf=False,
                )
            },
        ),
    )
    mapping = _mapping(
        "gross_profit",
        (
            _candidate(
                "akshare",
                "毛利",
                "GROSS_PROFIT",
                Decimal("200"),
                currency="CNY",
                unit="raw",
                canonical_unit="CNY",
                statement_metadata_proven=True,
            ),
            _candidate(
                "yahoo",
                "Gross Profit",
                None,
                Decimal("100"),
                # trusted_currency on the rule is HKD with no
                # additional_trusted_currencies in _trust_rule().
                currency="CNY",
                unit="raw",
                canonical_unit="CNY",
                unit_multiplier=Decimal("1"),
                statement_metadata_proven=True,
            ),
        ),
        policy_evidence_candidates=(),
    )
    reconciliation = reconcile_mapped_fields(mapping)

    standardized_policy = HkYahooTrustPolicy(
        version=1,
        market="HK",
        provider="yahoo",
        rules=(
            _trust_rule("gross_profit", "Gross Profit", "yahoo_standardized_accepted"),
        ),
    )
    report = build_source_policy_report(
        catalog,
        mapping,
        reconciliation,
        market="HK",
        company_id="00001",
        hk_yahoo_trust_policy=standardized_policy,
        provider_semantics_catalog=_provider_semantics(),
    )

    item = report.items["gross_profit"]
    assert item.verification_required is True
    assert item.selection_status != "selected_primary"


def test_source_policy_standardized_branch_accepts_gated_candidate() -> None:
    """Positive control: flag + matching yahoo_standardized_accepted rule
    (raw field, currency, unit shape) → selected_primary, usable."""
    catalog = _catalog(
        "gross_profit",
        SourcePolicy(
            semantic_concept="reported statement line",
            market_policies={
                "HK": MarketSourcePolicy(
                    primary_route="yahoo_direct",
                    cross_check_routes=("akshare_direct",),
                    on_conflict="select_primary_standardized",
                    single_source_requires_pdf=False,
                )
            },
        ),
    )
    mapping = _mapping(
        "gross_profit",
        (
            _candidate(
                "akshare",
                "毛利",
                "GROSS_PROFIT",
                Decimal("200"),
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
                statement_metadata_proven=True,
            ),
        ),
        policy_evidence_candidates=(),
    )
    reconciliation = reconcile_mapped_fields(mapping)

    standardized_policy = HkYahooTrustPolicy(
        version=1,
        market="HK",
        provider="yahoo",
        rules=(
            _trust_rule("gross_profit", "Gross Profit", "yahoo_standardized_accepted"),
        ),
    )
    report = build_source_policy_report(
        catalog,
        mapping,
        reconciliation,
        market="HK",
        company_id="00001",
        hk_yahoo_trust_policy=standardized_policy,
        provider_semantics_catalog=_provider_semantics(),
    )

    item = report.items["gross_profit"]
    assert item.selection_status == "selected_primary"
    assert item.selected_candidate is not None
    assert item.selected_candidate.source == "yahoo"
    assert item.verification_required is False
    assert item.conflict_classifications == ()


def test_source_policy_single_source_waiver_applies_to_primary_source_only() -> None:
    """single_source_requires_pdf=false waives PDF for the PRIMARY route's
    provider only; a lone cross-check-source candidate keeps
    single_source_unverified (2026-06-12 review hardening — previously a
    lone non-primary candidate was silently blessed)."""
    policy = SourcePolicy(
        semantic_concept="reported statement line",
        market_policies={
            "CN": MarketSourcePolicy(
                primary_route="akshare_direct",
                cross_check_routes=("yahoo_direct",),
                on_conflict="preserve_conflict",
                single_source_requires_pdf=False,
            )
        },
    )
    yahoo_only = _single_source_mapping(
        "gross_profit",
        _candidate(
            "yahoo",
            "Gross Profit",
            None,
            Decimal("100"),
            currency="CNY",
            unit="raw",
            canonical_unit="CNY",
            unit_multiplier=Decimal("1"),
            statement_metadata_proven=True,
        ),
    )
    report = build_source_policy_report(
        _catalog("gross_profit", policy),
        yahoo_only,
        reconcile_mapped_fields(yahoo_only),
        market="CN",
        company_id="600519",
        hk_yahoo_trust_policy=None,
        provider_semantics_catalog=None,
    )
    item = report.items["gross_profit"]
    assert item.selection_status == "selected_single_source"
    assert item.conflict_classifications == ("single_source_unverified",)
    assert item.verification_required is True

    akshare_only = _single_source_mapping(
        "gross_profit",
        _candidate(
            "akshare",
            "毛利",
            "GROSS_PROFIT",
            Decimal("100"),
            currency="CNY",
            unit="raw",
            canonical_unit="CNY",
            statement_metadata_proven=True,
        ),
    )
    report = build_source_policy_report(
        _catalog("gross_profit", policy),
        akshare_only,
        reconcile_mapped_fields(akshare_only),
        market="CN",
        company_id="600519",
        hk_yahoo_trust_policy=None,
        provider_semantics_catalog=None,
    )
    item = report.items["gross_profit"]
    assert item.selection_status == "selected_single_source"
    assert item.conflict_classifications == ()
    assert item.verification_required is False


def test_source_policy_standardized_branch_extends_to_cn_when_rule_allows() -> None:
    """2026-06-12 (evening) operator decision: gross_profit CN follows the
    HK standardized acceptance. The trust rule's applies_to_markets
    carries the market coverage — ["HK", "CN"] accepts a CN conflict's
    Yahoo candidate; the default HK-only rule must NOT."""
    catalog = _catalog(
        "gross_profit",
        SourcePolicy(
            semantic_concept="reported statement line",
            market_policies={
                "CN": MarketSourcePolicy(
                    primary_route="yahoo_direct",
                    cross_check_routes=("akshare_direct",),
                    on_conflict="select_primary_standardized",
                    single_source_requires_pdf=False,
                )
            },
        ),
    )
    mapping = _mapping(
        "gross_profit",
        (
            _candidate(
                "akshare",
                "毛利",
                "GROSS_PROFIT",
                Decimal("200"),
                currency="CNY",
                unit="yuan",
                canonical_unit="CNY",
                statement_metadata_proven=True,
            ),
            _candidate(
                "yahoo",
                "Gross Profit",
                None,
                Decimal("100"),
                currency="CNY",
                unit="raw",
                canonical_unit="CNY",
                unit_multiplier=Decimal("1"),
                statement_metadata_proven=True,
            ),
        ),
        policy_evidence_candidates=(),
    )
    reconciliation = reconcile_mapped_fields(mapping)

    cn_rule = HkYahooTrustRule(
        policy_id="hk_yahoo_standardized_accepted:gross_profit",
        field_id="gross_profit",
        classification="yahoo_standardized_accepted",
        trusted_currency="HKD",
        trusted_unit="raw",
        trusted_unit_multiplier=Decimal("1"),
        allowed_yahoo_raw_fields=("Gross Profit",),
        definition_status_reason="operator decision (test)",
        additional_trusted_currencies=("CNY", "USD"),
        applies_to_markets=("HK", "CN"),
    )
    policy_with_cn = HkYahooTrustPolicy(
        version=1, market="HK", provider="yahoo", rules=(cn_rule,),
    )
    report = build_source_policy_report(
        catalog,
        mapping,
        reconciliation,
        market="CN",
        company_id="600519",
        hk_yahoo_trust_policy=policy_with_cn,
        provider_semantics_catalog=None,
    )
    item = report.items["gross_profit"]
    assert item.selection_status == "selected_primary"
    assert item.selected_candidate is not None
    assert item.selected_candidate.source == "yahoo"
    assert item.verification_required is False

    # Default applies_to_markets=("HK",) must refuse the CN conflict.
    hk_only_rule = HkYahooTrustRule(
        policy_id="hk_yahoo_standardized_accepted:gross_profit",
        field_id="gross_profit",
        classification="yahoo_standardized_accepted",
        trusted_currency="HKD",
        trusted_unit="raw",
        trusted_unit_multiplier=Decimal("1"),
        allowed_yahoo_raw_fields=("Gross Profit",),
        definition_status_reason="operator decision (test)",
        additional_trusted_currencies=("CNY", "USD"),
    )
    policy_hk_only = HkYahooTrustPolicy(
        version=1, market="HK", provider="yahoo", rules=(hk_only_rule,),
    )
    report = build_source_policy_report(
        catalog,
        mapping,
        reconciliation,
        market="CN",
        company_id="600519",
        hk_yahoo_trust_policy=policy_hk_only,
        provider_semantics_catalog=None,
    )
    item = report.items["gross_profit"]
    assert item.selection_status != "selected_primary"
    assert item.verification_required is True
