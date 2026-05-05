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
    unit: str | None = "default",
    canonical_unit: str | None = "default",
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
